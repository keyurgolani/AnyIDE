"""Memory tools — graph-based knowledge storage and retrieval."""

import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from anyide.core.database import Database
from anyide.logging_config import get_logger
from anyide.models import (
    MemoryStoreRequest,
    MemoryStoreResponse,
    MemoryGetRequest,
    MemoryGetResponse,
    MemoryNode,
    MemoryRelation,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryUpdateRequest,
    MemoryUpdateResponse,
    MemoryDeleteRequest,
    MemoryDeleteResponse,
    MemoryLinkRequest,
    MemoryLinkResponse,
    MemoryChildrenRequest,
    MemoryAncestorsRequest,
    MemoryRelatedRequest,
    MemorySubtreeRequest,
    MemoryNodesResponse,
    MemoryStatsResponse,
)

logger = get_logger(__name__)


class NodeNotFoundError(ValueError):
    """Raised when a requested memory node does not exist."""


# Common conversational words that add noise in memory search prompts.
_FTS_NOISE_TOKENS = {
    "a", "an", "and", "are", "be", "can", "do", "does", "for", "from",
    "how", "i", "in", "is", "it", "know", "me", "my", "of", "on", "or",
    "that", "the", "to", "what", "when", "where", "who", "why", "with",
    "you", "your",
}


def _new_id() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_json_field(value: Optional[str], default: Any) -> Any:
    """Parse a JSON field, returning default on failure."""
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _tokenize_search_query(query: str) -> List[str]:
    """Tokenize text into FTS-safe alphanumeric terms, preserving order."""
    return re.findall(r"\w+", query, flags=re.UNICODE)


def _dedupe_preserve_order(tokens: List[str]) -> List[str]:
    """Deduplicate tokens while preserving first occurrence order."""
    seen = set()
    out = []
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


def _build_fts_query_candidates(query: str) -> List[str]:
    """Build FTS5 query candidates from strict to broad for better recall."""
    raw_tokens = _dedupe_preserve_order(_tokenize_search_query(query))
    if not raw_tokens:
        raw = query.strip()
        return [raw] if raw else []

    key_tokens = [t for t in raw_tokens if t.lower() not in _FTS_NOISE_TOKENS]
    if not key_tokens:
        key_tokens = raw_tokens

    candidates: List[str] = []

    def add(expr: str) -> None:
        expr = expr.strip()
        if expr and expr not in candidates:
            candidates.append(expr)

    if len(key_tokens) > 1:
        add(" AND ".join(key_tokens))
        add(" OR ".join(key_tokens))
    else:
        add(key_tokens[0])

    if key_tokens != raw_tokens:
        if len(raw_tokens) > 1:
            add(" AND ".join(raw_tokens))
            add(" OR ".join(raw_tokens))
        else:
            add(raw_tokens[0])

    return candidates


def _row_to_node(row) -> MemoryNode:
    """Convert a database row to a MemoryNode model."""
    return MemoryNode(
        id=row["id"],
        name=row["name"],
        content=row["content"],
        entity_type=row["entity_type"],
        tags=_parse_json_field(row["tags"], []),
        metadata=_parse_json_field(row["metadata"], {}),
        source=row["source"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class MemoryTools:
    """Graph-based knowledge storage and retrieval tools."""

    def __init__(self, db: Database):
        """Initialise with a shared Database instance.

        Args:
            db: Connected Database instance (shared with the rest of the app)
        """
        self.db = db

    # ------------------------------------------------------------------
    # memory_store
    # ------------------------------------------------------------------

    async def store(self, req: MemoryStoreRequest) -> MemoryStoreResponse:
        """Store a new knowledge node.

        Optionally creates edges to existing nodes in the same transaction.

        Args:
            req: Store request with content, optional metadata, and relations

        Returns:
            MemoryStoreResponse with the new node's ID and creation timestamp

        Raises:
            NodeNotFoundError: If any relation target_id does not exist
        """
        node_id = _new_id()
        now = _now_iso()
        name = req.name or req.content[:60]
        tags_json = json.dumps(req.tags or [])
        metadata_json = json.dumps(req.metadata or {})

        conn = self.db.connection

        # Validate relation targets exist before inserting
        if req.relations:
            for rel in req.relations:
                row = await conn.execute(
                    "SELECT id FROM memory_nodes WHERE id = ?", (rel.target_id,)
                )
                if not await row.fetchone():
                    raise NodeNotFoundError(
                        f"Relation target node '{rel.target_id}' does not exist"
                    )

        await conn.execute(
            """
            INSERT INTO memory_nodes (id, name, content, entity_type, tags, metadata, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (node_id, name, req.content, req.entity_type, tags_json, metadata_json, req.source, now, now),
        )

        relations_created = 0
        if req.relations:
            for rel in req.relations:
                edge_id = _new_id()
                await conn.execute(
                    """
                    INSERT INTO memory_edges (id, source_id, target_id, relation, weight, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, '{}', ?)
                    ON CONFLICT(source_id, target_id, relation) DO UPDATE
                        SET weight = excluded.weight
                    """,
                    (edge_id, node_id, rel.target_id, rel.relation, rel.weight, now),
                )
                relations_created += 1

        await conn.commit()
        logger.info("memory_store", node_id=node_id, entity_type=req.entity_type)

        return MemoryStoreResponse(
            id=node_id,
            name=name,
            created_at=now,
            relations_created=relations_created,
        )

    # ------------------------------------------------------------------
    # memory_get
    # ------------------------------------------------------------------

    async def get(self, req: MemoryGetRequest) -> MemoryGetResponse:
        """Retrieve a node by ID with its immediate relationships.

        Args:
            req: Get request specifying node ID, depth, and whether to include relations

        Returns:
            MemoryGetResponse with the node and its relations

        Raises:
            NodeNotFoundError: If the node does not exist
        """
        conn = self.db.connection

        row = await conn.execute(
            "SELECT * FROM memory_nodes WHERE id = ?", (req.id,)
        )
        node_row = await row.fetchone()
        if not node_row:
            raise NodeNotFoundError(f"Node '{req.id}' not found")

        node = _row_to_node(node_row)
        relations: List[MemoryRelation] = []

        if req.include_relations:
            # Outgoing edges
            cur = await conn.execute(
                """
                SELECT e.id as edge_id, e.relation, e.weight,
                       n.id as n_id, n.name as n_name, n.entity_type as n_type,
                       SUBSTR(n.content, 1, 120) as n_preview
                FROM memory_edges e
                JOIN memory_nodes n ON n.id = e.target_id
                WHERE e.source_id = ?
                """,
                (req.id,),
            )
            for r in await cur.fetchall():
                relations.append(MemoryRelation(
                    edge_id=r["edge_id"],
                    direction="outgoing",
                    relation=r["relation"],
                    weight=r["weight"],
                    neighbor={
                        "id": r["n_id"],
                        "name": r["n_name"],
                        "entity_type": r["n_type"],
                        "content_preview": r["n_preview"],
                    },
                ))

            # Incoming edges
            cur = await conn.execute(
                """
                SELECT e.id as edge_id, e.relation, e.weight,
                       n.id as n_id, n.name as n_name, n.entity_type as n_type,
                       SUBSTR(n.content, 1, 120) as n_preview
                FROM memory_edges e
                JOIN memory_nodes n ON n.id = e.source_id
                WHERE e.target_id = ?
                """,
                (req.id,),
            )
            for r in await cur.fetchall():
                relations.append(MemoryRelation(
                    edge_id=r["edge_id"],
                    direction="incoming",
                    relation=r["relation"],
                    weight=r["weight"],
                    neighbor={
                        "id": r["n_id"],
                        "name": r["n_name"],
                        "entity_type": r["n_type"],
                        "content_preview": r["n_preview"],
                    },
                ))

        return MemoryGetResponse(node=node, relations=relations)

    # ------------------------------------------------------------------
    # memory_search
    # ------------------------------------------------------------------

    async def search(self, req: MemorySearchRequest) -> MemorySearchResponse:
        """Hybrid search across the knowledge graph.

        Supports full-text search (FTS5 BM25), tag-based filtering, or both.

        Args:
            req: Search request with query text, filters, and search mode

        Returns:
            MemorySearchResponse with ranked results
        """
        start_ms = int(time.time() * 1000)
        conn = self.db.connection
        results: List[MemorySearchResult] = []

        mode = req.search_mode

        # ------ Full-text search branch ------
        if mode in ("fulltext", "hybrid"):
            query_candidates = _build_fts_query_candidates(req.query)
            if not query_candidates and req.query.strip():
                query_candidates = [req.query.strip()]

            fts_sql = """
                SELECT n.*, -bm25(memory_nodes_fts) AS score, 'content' as matched_field
                FROM memory_nodes_fts
                JOIN memory_nodes n ON memory_nodes_fts.rowid = n.rowid
                WHERE memory_nodes_fts MATCH ?
            """
            base_params: list = []

            if req.entity_type:
                fts_sql += " AND n.entity_type = ?"
                base_params.append(req.entity_type)

            if req.tags:
                for tag in req.tags:
                    fts_sql += " AND EXISTS (SELECT 1 FROM json_each(n.tags) WHERE value = ?)"
                    base_params.append(tag)

            if req.temporal_filter:
                fts_sql += " AND n.created_at <= ?"
                base_params.append(req.temporal_filter)

            fts_sql += " ORDER BY score DESC LIMIT ?"
            seen_ids = set()

            for candidate in query_candidates:
                if len(results) >= req.max_results:
                    break
                params = [candidate, *base_params, req.max_results]
                try:
                    cur = await conn.execute(fts_sql, params)
                    rows = await cur.fetchall()
                    for row in rows:
                        if row["id"] in seen_ids:
                            continue
                        seen_ids.add(row["id"])
                        results.append(MemorySearchResult(
                            node=_row_to_node(row),
                            relevance_score=float(row["score"]),
                            matched_field=row["matched_field"],
                        ))
                        if len(results) >= req.max_results:
                            break
                except Exception:
                    # FTS5 MATCH syntax errors should fall through gracefully
                    continue

        # ------ Tags-only branch ------
        if mode == "tags" and req.tags:
            tags_sql = "SELECT DISTINCT n.* FROM memory_nodes n WHERE 1=1"
            params = []
            for tag in req.tags:
                tags_sql += " AND EXISTS (SELECT 1 FROM json_each(n.tags) WHERE value = ?)"
                params.append(tag)

            if req.entity_type:
                tags_sql += " AND n.entity_type = ?"
                params.append(req.entity_type)

            if req.temporal_filter:
                tags_sql += " AND n.created_at <= ?"
                params.append(req.temporal_filter)

            tags_sql += " LIMIT ?"
            params.append(req.max_results)

            cur = await conn.execute(tags_sql, params)
            rows = await cur.fetchall()
            existing_ids = {r.node.id for r in results}
            for row in rows:
                if row["id"] not in existing_ids:
                    results.append(MemorySearchResult(
                        node=_row_to_node(row),
                        relevance_score=1.0,
                        matched_field="tags",
                    ))

        # If hybrid but no FTS results and tags provided, also do tag search
        if mode == "hybrid" and req.tags and not results:
            tag_results = await self.search(
                MemorySearchRequest(
                    query=req.query,
                    entity_type=req.entity_type,
                    tags=req.tags,
                    max_results=req.max_results,
                    search_mode="tags",
                    temporal_filter=req.temporal_filter,
                )
            )
            results = tag_results.results

        elapsed = int(time.time() * 1000) - start_ms
        return MemorySearchResponse(
            results=results[: req.max_results],
            total_matches=len(results),
            search_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # memory_update
    # ------------------------------------------------------------------

    async def update(self, req: MemoryUpdateRequest) -> MemoryUpdateResponse:
        """Update a node's content or metadata.

        Metadata updates are merged with existing values (patch semantics).

        Args:
            req: Update request specifying which fields to change

        Returns:
            MemoryUpdateResponse with previous content and updated timestamp

        Raises:
            NodeNotFoundError: If the node does not exist
        """
        conn = self.db.connection

        row = await conn.execute(
            "SELECT * FROM memory_nodes WHERE id = ?", (req.id,)
        )
        existing = await row.fetchone()
        if not existing:
            raise NodeNotFoundError(f"Node '{req.id}' not found")

        previous_content = existing["content"]
        now = _now_iso()

        new_content = req.content if req.content is not None else existing["content"]
        new_name = req.name if req.name is not None else existing["name"]
        new_tags = json.dumps(req.tags) if req.tags is not None else existing["tags"]

        # Merge metadata
        if req.metadata is not None:
            old_meta = _parse_json_field(existing["metadata"], {})
            old_meta.update(req.metadata)
            new_metadata = json.dumps(old_meta)
        else:
            new_metadata = existing["metadata"]

        await conn.execute(
            """
            UPDATE memory_nodes
            SET content = ?, name = ?, tags = ?, metadata = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_content, new_name, new_tags, new_metadata, now, req.id),
        )
        await conn.commit()
        logger.info("memory_update", node_id=req.id)

        return MemoryUpdateResponse(
            node={"id": req.id, "name": new_name, "updated_at": now},
            previous_content=previous_content,
        )

    # ------------------------------------------------------------------
    # memory_delete
    # ------------------------------------------------------------------

    async def delete(self, req: MemoryDeleteRequest) -> MemoryDeleteResponse:
        """Delete a node and its edges.

        With cascade=False, lists potential orphaned children but does not
        delete them. With cascade=True, also deletes nodes that were only
        connected via parent_of edges from this node.

        Args:
            req: Delete request with node ID and cascade flag

        Returns:
            MemoryDeleteResponse with deletion counts and orphan information

        Raises:
            NodeNotFoundError: If the node does not exist
        """
        conn = self.db.connection

        row = await conn.execute(
            "SELECT * FROM memory_nodes WHERE id = ?", (req.id,)
        )
        existing = await row.fetchone()
        if not existing:
            raise NodeNotFoundError(f"Node '{req.id}' not found")

        deleted_node = {"id": req.id, "name": existing["name"]}

        # Find edge count before deletion
        cur = await conn.execute(
            "SELECT COUNT(*) as cnt FROM memory_edges WHERE source_id = ? OR target_id = ?",
            (req.id, req.id),
        )
        edge_count_row = await cur.fetchone()
        deleted_edges = edge_count_row["cnt"]

        # Find orphaned children: nodes that were exclusively children of this node
        cur = await conn.execute(
            """
            SELECT n.id, n.name FROM memory_nodes n
            WHERE EXISTS (
                SELECT 1 FROM memory_edges e
                WHERE e.source_id = ? AND e.target_id = n.id AND e.relation = 'parent_of'
            )
            AND NOT EXISTS (
                SELECT 1 FROM memory_edges e2
                WHERE e2.source_id != ? AND e2.target_id = n.id AND e2.relation = 'parent_of'
            )
            """,
            (req.id, req.id),
        )
        orphaned_rows = await cur.fetchall()
        orphaned_children = [{"id": r["id"], "name": r["name"]} for r in orphaned_rows]

        if req.cascade:
            for child in orphaned_children:
                # Recursively delete orphaned children
                await conn.execute(
                    "DELETE FROM memory_nodes WHERE id = ?", (child["id"],)
                )

        # Delete the node (edges cascade automatically via FK constraint)
        await conn.execute("DELETE FROM memory_nodes WHERE id = ?", (req.id,))
        await conn.commit()

        if req.cascade:
            orphaned_children = []  # All were deleted

        logger.info("memory_delete", node_id=req.id, cascade=req.cascade)

        return MemoryDeleteResponse(
            deleted_node=deleted_node,
            deleted_edges=deleted_edges,
            orphaned_children=orphaned_children,
        )

    # ------------------------------------------------------------------
    # memory_link
    # ------------------------------------------------------------------

    async def link(self, req: MemoryLinkRequest) -> MemoryLinkResponse:
        """Create or update a relationship between two nodes.

        If the edge already exists (same source, target, relation), updates its
        weight and metadata. If bidirectional=True, also creates/updates the
        reverse edge.

        Args:
            req: Link request specifying source, target, and relation type

        Returns:
            MemoryLinkResponse with edge details and created/updated flag

        Raises:
            NodeNotFoundError: If source or target node does not exist
        """
        conn = self.db.connection

        for nid, label in [(req.source_id, "source"), (req.target_id, "target")]:
            row = await conn.execute(
                "SELECT id FROM memory_nodes WHERE id = ?", (nid,)
            )
            if not await row.fetchone():
                raise NodeNotFoundError(f"Node '{nid}' ({label}) not found")

        now = _now_iso()
        metadata_json = json.dumps(req.metadata or {})

        # Check if edge already exists
        row = await conn.execute(
            "SELECT id FROM memory_edges WHERE source_id = ? AND target_id = ? AND relation = ?",
            (req.source_id, req.target_id, req.relation),
        )
        existing = await row.fetchone()
        created = existing is None

        edge_id = existing["id"] if existing else _new_id()

        await conn.execute(
            """
            INSERT INTO memory_edges (id, source_id, target_id, relation, weight, metadata, created_at, valid_from, valid_until)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation) DO UPDATE
                SET weight = excluded.weight,
                    metadata = excluded.metadata,
                    valid_from = excluded.valid_from,
                    valid_until = excluded.valid_until
            """,
            (
                edge_id,
                req.source_id,
                req.target_id,
                req.relation,
                req.weight,
                metadata_json,
                now,
                req.valid_from,
                req.valid_until,
            ),
        )

        if req.bidirectional:
            rev_row = await conn.execute(
                "SELECT id FROM memory_edges WHERE source_id = ? AND target_id = ? AND relation = ?",
                (req.target_id, req.source_id, req.relation),
            )
            rev_existing = await rev_row.fetchone()
            rev_id = rev_existing["id"] if rev_existing else _new_id()
            await conn.execute(
                """
                INSERT INTO memory_edges (id, source_id, target_id, relation, weight, metadata, created_at, valid_from, valid_until)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation) DO UPDATE
                    SET weight = excluded.weight,
                        metadata = excluded.metadata,
                        valid_from = excluded.valid_from,
                        valid_until = excluded.valid_until
                """,
                (
                    rev_id,
                    req.target_id,
                    req.source_id,
                    req.relation,
                    req.weight,
                    metadata_json,
                    now,
                    req.valid_from,
                    req.valid_until,
                ),
            )

        await conn.commit()
        logger.info("memory_link", source=req.source_id, target=req.target_id, relation=req.relation)

        return MemoryLinkResponse(
            edge={"id": edge_id, "source_id": req.source_id, "target_id": req.target_id, "relation": req.relation},
            created=created,
        )

    # ------------------------------------------------------------------
    # memory_children
    # ------------------------------------------------------------------

    async def children(self, req: MemoryChildrenRequest) -> MemoryNodesResponse:
        """Get immediate child nodes connected via parent_of edges.

        Args:
            req: Request with node ID

        Returns:
            MemoryNodesResponse with child nodes

        Raises:
            NodeNotFoundError: If the node does not exist
        """
        conn = self.db.connection
        await self._assert_exists(conn, req.id)

        cur = await conn.execute(
            """
            SELECT n.*
            FROM memory_nodes n
            JOIN memory_edges e ON e.target_id = n.id
            WHERE e.source_id = ? AND e.relation = 'parent_of'
            ORDER BY n.created_at
            """,
            (req.id,),
        )
        rows = await cur.fetchall()
        nodes = [_row_to_node(r) for r in rows]
        return MemoryNodesResponse(nodes=nodes, total=len(nodes))

    # ------------------------------------------------------------------
    # memory_ancestors
    # ------------------------------------------------------------------

    async def ancestors(self, req: MemoryAncestorsRequest) -> MemoryNodesResponse:
        """Traverse parent_of edges upward to find all ancestors (recursive CTE).

        Args:
            req: Request with node ID and max_depth limit

        Returns:
            MemoryNodesResponse with all ancestor nodes

        Raises:
            NodeNotFoundError: If the node does not exist
        """
        conn = self.db.connection
        await self._assert_exists(conn, req.id)

        cur = await conn.execute(
            """
            WITH RECURSIVE ancestors(id, depth) AS (
                SELECT e.source_id, 1
                FROM memory_edges e
                WHERE e.target_id = ? AND e.relation = 'parent_of'

                UNION

                SELECT e.source_id, a.depth + 1
                FROM memory_edges e
                JOIN ancestors a ON e.target_id = a.id
                WHERE e.relation = 'parent_of' AND a.depth < ?
            )
            SELECT DISTINCT n.*
            FROM memory_nodes n
            JOIN ancestors a ON n.id = a.id
            ORDER BY n.created_at
            """,
            (req.id, req.max_depth),
        )
        rows = await cur.fetchall()
        nodes = [_row_to_node(r) for r in rows]
        return MemoryNodesResponse(nodes=nodes, total=len(nodes))

    # ------------------------------------------------------------------
    # memory_roots
    # ------------------------------------------------------------------

    async def roots(self) -> MemoryNodesResponse:
        """Get all root nodes — nodes with no incoming parent_of edges.

        Returns:
            MemoryNodesResponse with all root nodes
        """
        conn = self.db.connection

        cur = await conn.execute(
            """
            SELECT n.*
            FROM memory_nodes n
            WHERE NOT EXISTS (
                SELECT 1 FROM memory_edges e
                WHERE e.target_id = n.id AND e.relation = 'parent_of'
            )
            ORDER BY n.created_at
            """
        )
        rows = await cur.fetchall()
        nodes = [_row_to_node(r) for r in rows]
        return MemoryNodesResponse(nodes=nodes, total=len(nodes))

    # ------------------------------------------------------------------
    # memory_related
    # ------------------------------------------------------------------

    async def related(self, req: MemoryRelatedRequest) -> MemoryNodesResponse:
        """Get all nodes connected to the given node by any edge type.

        Args:
            req: Request with node ID and optional relation filter

        Returns:
            MemoryNodesResponse with connected nodes

        Raises:
            NodeNotFoundError: If the node does not exist
        """
        conn = self.db.connection
        await self._assert_exists(conn, req.id)

        if req.relation:
            cur = await conn.execute(
                """
                SELECT DISTINCT n.*
                FROM memory_nodes n
                WHERE n.id IN (
                    SELECT target_id FROM memory_edges WHERE source_id = ? AND relation = ?
                    UNION
                    SELECT source_id FROM memory_edges WHERE target_id = ? AND relation = ?
                )
                ORDER BY n.name
                """,
                (req.id, req.relation, req.id, req.relation),
            )
        else:
            cur = await conn.execute(
                """
                SELECT DISTINCT n.*
                FROM memory_nodes n
                WHERE n.id IN (
                    SELECT target_id FROM memory_edges WHERE source_id = ?
                    UNION
                    SELECT source_id FROM memory_edges WHERE target_id = ?
                )
                ORDER BY n.name
                """,
                (req.id, req.id),
            )

        rows = await cur.fetchall()
        nodes = [_row_to_node(r) for r in rows]
        return MemoryNodesResponse(nodes=nodes, total=len(nodes))

    # ------------------------------------------------------------------
    # memory_subtree
    # ------------------------------------------------------------------

    async def subtree(self, req: MemorySubtreeRequest) -> MemoryNodesResponse:
        """Return the full subtree rooted at the given node using a recursive CTE.

        Follows parent_of edges downward (from parent to children).

        Args:
            req: Request with node ID and max_depth limit

        Returns:
            MemoryNodesResponse with all descendant nodes (excluding the root)

        Raises:
            NodeNotFoundError: If the node does not exist
        """
        conn = self.db.connection
        await self._assert_exists(conn, req.id)

        cur = await conn.execute(
            """
            WITH RECURSIVE subtree(id, depth) AS (
                SELECT e.target_id, 1
                FROM memory_edges e
                WHERE e.source_id = ? AND e.relation = 'parent_of'

                UNION

                SELECT e.target_id, s.depth + 1
                FROM memory_edges e
                JOIN subtree s ON e.source_id = s.id
                WHERE e.relation = 'parent_of' AND s.depth < ?
            )
            SELECT DISTINCT n.*
            FROM memory_nodes n
            JOIN subtree s ON n.id = s.id
            ORDER BY n.created_at
            """,
            (req.id, req.max_depth),
        )
        rows = await cur.fetchall()
        nodes = [_row_to_node(r) for r in rows]
        return MemoryNodesResponse(nodes=nodes, total=len(nodes))

    # ------------------------------------------------------------------
    # memory_stats
    # ------------------------------------------------------------------

    async def stats(self) -> MemoryStatsResponse:
        """Return knowledge graph statistics.

        Returns:
            MemoryStatsResponse with node/edge counts, type breakdown, and top nodes
        """
        conn = self.db.connection

        # Total counts
        row = await conn.execute("SELECT COUNT(*) as cnt FROM memory_nodes")
        total_nodes = (await row.fetchone())["cnt"]

        row = await conn.execute("SELECT COUNT(*) as cnt FROM memory_edges")
        total_edges = (await row.fetchone())["cnt"]

        # Nodes by type
        cur = await conn.execute(
            "SELECT entity_type, COUNT(*) as cnt FROM memory_nodes GROUP BY entity_type"
        )
        nodes_by_type: Dict[str, int] = {r["entity_type"]: r["cnt"] for r in await cur.fetchall()}

        # Edges by relation
        cur = await conn.execute(
            "SELECT relation, COUNT(*) as cnt FROM memory_edges GROUP BY relation"
        )
        edges_by_relation: Dict[str, int] = {r["relation"]: r["cnt"] for r in await cur.fetchall()}

        # Most connected nodes (by total edge count)
        cur = await conn.execute(
            """
            SELECT n.id, n.name,
                   (SELECT COUNT(*) FROM memory_edges e WHERE e.source_id = n.id OR e.target_id = n.id) as edge_count
            FROM memory_nodes n
            ORDER BY edge_count DESC
            LIMIT 10
            """
        )
        most_connected = [
            {"id": r["id"], "name": r["name"], "edge_count": r["edge_count"]}
            for r in await cur.fetchall()
        ]

        # Orphaned nodes (no edges at all)
        row = await conn.execute(
            """
            SELECT COUNT(*) as cnt FROM memory_nodes n
            WHERE NOT EXISTS (
                SELECT 1 FROM memory_edges e
                WHERE e.source_id = n.id OR e.target_id = n.id
            )
            """
        )
        orphaned_nodes = (await row.fetchone())["cnt"]

        # Created in last 24h
        row = await conn.execute(
            """
            SELECT COUNT(*) as cnt FROM memory_nodes
            WHERE created_at >= datetime('now', '-24 hours')
            """
        )
        created_last_24h = (await row.fetchone())["cnt"]

        # Tag frequency
        cur = await conn.execute(
            """
            SELECT jt.value as tag, COUNT(*) as cnt
            FROM memory_nodes n, json_each(n.tags) jt
            GROUP BY jt.value
            ORDER BY cnt DESC
            LIMIT 50
            """
        )
        tags_frequency: Dict[str, int] = {r["tag"]: r["cnt"] for r in await cur.fetchall()}

        return MemoryStatsResponse(
            total_nodes=total_nodes,
            total_edges=total_edges,
            nodes_by_type=nodes_by_type,
            edges_by_relation=edges_by_relation,
            most_connected_nodes=most_connected,
            orphaned_nodes=orphaned_nodes,
            created_last_24h=created_last_24h,
            tags_frequency=tags_frequency,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _assert_exists(self, conn, node_id: str) -> None:
        """Raise NodeNotFoundError if node does not exist."""
        row = await conn.execute(
            "SELECT id FROM memory_nodes WHERE id = ?", (node_id,)
        )
        if not await row.fetchone():
            raise NodeNotFoundError(f"Node '{node_id}' not found")
