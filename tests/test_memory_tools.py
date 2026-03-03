"""Tests for MemoryTools — knowledge graph storage, retrieval, and traversal."""

import os
import tempfile

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Set DB path BEFORE any app imports so the module-level Database() uses it
# ---------------------------------------------------------------------------
_TEST_DB_DIR = tempfile.mkdtemp()
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test_memory.db")
_TEST_WORKSPACE = tempfile.mkdtemp()

os.environ.setdefault("DB_PATH", _TEST_DB_PATH)
os.environ["DB_PATH"] = _TEST_DB_PATH
os.environ["WORKSPACE_BASE_DIR"] = _TEST_WORKSPACE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def memory_db():
    """A connected Database instance used for unit-level MemoryTools tests."""
    from anyide.core.database import Database

    db = Database(_TEST_DB_PATH)
    await db.connect()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def memory_tools(memory_db):
    """Fresh MemoryTools instance (but reuses the same DB connection)."""
    from anyide.modules.memory.tools import MemoryTools

    # Wipe tables before each test for isolation
    conn = memory_db.connection
    await conn.execute("DELETE FROM memory_edges")
    await conn.execute("DELETE FROM memory_nodes")
    await conn.execute("INSERT INTO memory_nodes_fts(memory_nodes_fts) VALUES('rebuild')")
    await conn.commit()

    return MemoryTools(memory_db)


# ---------------------------------------------------------------------------
# TestMemoryStore
# ---------------------------------------------------------------------------

class TestMemoryStore:
    """Tests for memory_store."""

    @pytest.mark.asyncio
    async def test_store_minimal(self, memory_tools):
        """Store with content only generates a node with defaults."""
        from anyide.models import MemoryStoreRequest

        req = MemoryStoreRequest(content="Python is a programming language")
        result = await memory_tools.store(req)

        assert result.id
        assert result.name == "Python is a programming language"
        assert result.relations_created == 0
        assert result.created_at

    @pytest.mark.asyncio
    async def test_store_with_name(self, memory_tools):
        """Explicit name overrides content-derived name."""
        from anyide.models import MemoryStoreRequest

        req = MemoryStoreRequest(content="Long content here", name="My Node")
        result = await memory_tools.store(req)

        assert result.name == "My Node"

    @pytest.mark.asyncio
    async def test_store_name_truncated_to_60_chars(self, memory_tools):
        """Content longer than 60 chars is truncated for the auto-name."""
        from anyide.models import MemoryStoreRequest

        content = "A" * 80
        req = MemoryStoreRequest(content=content)
        result = await memory_tools.store(req)

        assert len(result.name) == 60

    @pytest.mark.asyncio
    async def test_store_with_tags_and_metadata(self, memory_tools):
        """Tags and metadata are persisted correctly."""
        from anyide.models import MemoryStoreRequest, MemoryGetRequest

        req = MemoryStoreRequest(
            content="Test node",
            tags=["python", "testing"],
            metadata={"priority": "high"},
            entity_type="task",
        )
        stored = await memory_tools.store(req)

        # Retrieve and verify
        got = await memory_tools.get(MemoryGetRequest(id=stored.id, include_relations=False))
        assert got.node.tags == ["python", "testing"]
        assert got.node.metadata == {"priority": "high"}
        assert got.node.entity_type == "task"

    @pytest.mark.asyncio
    async def test_store_with_relations(self, memory_tools):
        """Storing with relations creates edges to existing nodes."""
        from anyide.models import MemoryStoreRequest, MemoryStoreRelation

        # Create a target node first
        target = await memory_tools.store(MemoryStoreRequest(content="Target node"))

        req = MemoryStoreRequest(
            content="Source node",
            relations=[MemoryStoreRelation(target_id=target.id, relation="related_to", weight=0.8)],
        )
        result = await memory_tools.store(req)

        assert result.relations_created == 1

    @pytest.mark.asyncio
    async def test_store_with_invalid_relation_target_raises(self, memory_tools):
        """Referencing a non-existent target ID raises NodeNotFoundError."""
        from anyide.models import MemoryStoreRequest, MemoryStoreRelation
        from anyide.modules.memory.tools import NodeNotFoundError

        req = MemoryStoreRequest(
            content="Source node",
            relations=[MemoryStoreRelation(target_id="nonexistent-id", relation="related_to")],
        )
        with pytest.raises(NodeNotFoundError, match="nonexistent-id"):
            await memory_tools.store(req)


# ---------------------------------------------------------------------------
# TestMemoryGet
# ---------------------------------------------------------------------------

class TestMemoryGet:
    """Tests for memory_get."""

    @pytest.mark.asyncio
    async def test_get_existing_node(self, memory_tools):
        """Retrieving a stored node returns full node details."""
        from anyide.models import MemoryStoreRequest, MemoryGetRequest

        stored = await memory_tools.store(MemoryStoreRequest(
            content="Knowledge about Python", name="Python node"
        ))
        result = await memory_tools.get(MemoryGetRequest(id=stored.id))

        assert result.node.id == stored.id
        assert result.node.name == "Python node"
        assert result.node.content == "Knowledge about Python"

    @pytest.mark.asyncio
    async def test_get_nonexistent_raises(self, memory_tools):
        """Retrieving a non-existent node raises NodeNotFoundError."""
        from anyide.models import MemoryGetRequest
        from anyide.modules.memory.tools import NodeNotFoundError

        with pytest.raises(NodeNotFoundError):
            await memory_tools.get(MemoryGetRequest(id="does-not-exist"))

    @pytest.mark.asyncio
    async def test_get_includes_outgoing_relations(self, memory_tools):
        """Relations include outgoing edges."""
        from anyide.models import MemoryStoreRequest, MemoryStoreRelation, MemoryGetRequest

        target = await memory_tools.store(MemoryStoreRequest(content="Target"))
        source = await memory_tools.store(MemoryStoreRequest(
            content="Source",
            relations=[MemoryStoreRelation(target_id=target.id, relation="related_to")],
        ))

        result = await memory_tools.get(MemoryGetRequest(id=source.id))
        outgoing = [r for r in result.relations if r.direction == "outgoing"]
        assert len(outgoing) == 1
        assert outgoing[0].relation == "related_to"
        assert outgoing[0].neighbor["id"] == target.id

    @pytest.mark.asyncio
    async def test_get_includes_incoming_relations(self, memory_tools):
        """Relations include incoming edges."""
        from anyide.models import MemoryStoreRequest, MemoryStoreRelation, MemoryGetRequest

        target = await memory_tools.store(MemoryStoreRequest(content="Target"))
        await memory_tools.store(MemoryStoreRequest(
            content="Source",
            relations=[MemoryStoreRelation(target_id=target.id, relation="depends_on")],
        ))

        result = await memory_tools.get(MemoryGetRequest(id=target.id))
        incoming = [r for r in result.relations if r.direction == "incoming"]
        assert len(incoming) == 1
        assert incoming[0].relation == "depends_on"

    @pytest.mark.asyncio
    async def test_get_without_relations(self, memory_tools):
        """include_relations=False returns empty relations list."""
        from anyide.models import MemoryStoreRequest, MemoryGetRequest

        stored = await memory_tools.store(MemoryStoreRequest(content="Solo node"))
        result = await memory_tools.get(MemoryGetRequest(id=stored.id, include_relations=False))

        assert result.relations == []


# ---------------------------------------------------------------------------
# TestMemorySearch
# ---------------------------------------------------------------------------

class TestMemorySearch:
    """Tests for memory_search."""

    @pytest.mark.asyncio
    async def test_fulltext_search_finds_matching_node(self, memory_tools):
        """Full-text search returns nodes matching the query."""
        from anyide.models import MemoryStoreRequest, MemorySearchRequest

        await memory_tools.store(MemoryStoreRequest(
            content="Machine learning is a subset of artificial intelligence",
            tags=["ML", "AI"],
        ))
        await memory_tools.store(MemoryStoreRequest(content="Unrelated topic"))

        result = await memory_tools.search(MemorySearchRequest(
            query="machine learning",
            search_mode="fulltext",
        ))

        assert result.total_matches >= 1
        texts = [r.node.content for r in result.results]
        assert any("machine learning" in t.lower() for t in texts)

    @pytest.mark.asyncio
    async def test_tag_search(self, memory_tools):
        """Tags-only search filters by exact tag values."""
        from anyide.models import MemoryStoreRequest, MemorySearchRequest

        await memory_tools.store(MemoryStoreRequest(
            content="Python tutorial", tags=["python", "tutorial"]
        ))
        await memory_tools.store(MemoryStoreRequest(
            content="JavaScript tutorial", tags=["javascript"]
        ))

        result = await memory_tools.search(MemorySearchRequest(
            query="",
            tags=["python"],
            search_mode="tags",
        ))

        assert result.total_matches == 1
        assert result.results[0].node.tags == ["python", "tutorial"]

    @pytest.mark.asyncio
    async def test_search_entity_type_filter(self, memory_tools):
        """entity_type filter narrows search results."""
        from anyide.models import MemoryStoreRequest, MemorySearchRequest

        await memory_tools.store(MemoryStoreRequest(
            content="Deploy the app", entity_type="task"
        ))
        await memory_tools.store(MemoryStoreRequest(
            content="Deployment concept", entity_type="concept"
        ))

        result = await memory_tools.search(MemorySearchRequest(
            query="deploy",
            entity_type="task",
            search_mode="fulltext",
        ))

        assert all(r.node.entity_type == "task" for r in result.results)

    @pytest.mark.asyncio
    async def test_search_max_results_respected(self, memory_tools):
        """max_results caps the number of returned results."""
        from anyide.models import MemoryStoreRequest, MemorySearchRequest

        for i in range(6):
            await memory_tools.store(MemoryStoreRequest(
                content=f"Python tip number {i}"
            ))

        result = await memory_tools.search(MemorySearchRequest(
            query="Python tip",
            max_results=3,
            search_mode="fulltext",
        ))

        assert len(result.results) <= 3

    @pytest.mark.asyncio
    async def test_search_empty_graph_returns_empty(self, memory_tools):
        """Searching an empty graph returns zero results."""
        from anyide.models import MemorySearchRequest

        result = await memory_tools.search(MemorySearchRequest(query="anything"))
        assert result.total_matches == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_fulltext_search_handles_natural_language_question_for_full_name(self, memory_tools):
        """Question-shaped queries should still match person names in stored memory."""
        from anyide.models import MemoryStoreRequest, MemorySearchRequest

        await memory_tools.store(MemoryStoreRequest(
            content="I am Keyur Golani and I own a Honda Accord Hybrid car.",
        ))

        result = await memory_tools.search(MemorySearchRequest(
            query="What do you know about Keyur Golani?",
            search_mode="fulltext",
        ))

        assert result.total_matches >= 1
        assert any("Keyur Golani" in r.node.content for r in result.results)

    @pytest.mark.asyncio
    async def test_fulltext_search_handles_natural_language_question_for_single_name(self, memory_tools):
        """Question-shaped queries should match even when wrapped around a single keyword."""
        from anyide.models import MemoryStoreRequest, MemorySearchRequest

        await memory_tools.store(MemoryStoreRequest(
            content="Keyur likes Honda cars.",
        ))

        result = await memory_tools.search(MemorySearchRequest(
            query="What do you know about Keyur?",
            search_mode="fulltext",
        ))

        assert result.total_matches >= 1
        assert any("Keyur" in r.node.content for r in result.results)


# ---------------------------------------------------------------------------
# TestMemoryUpdate
# ---------------------------------------------------------------------------

class TestMemoryUpdate:
    """Tests for memory_update."""

    @pytest.mark.asyncio
    async def test_update_content(self, memory_tools):
        """Updating content changes the stored value."""
        from anyide.models import MemoryStoreRequest, MemoryUpdateRequest, MemoryGetRequest

        stored = await memory_tools.store(MemoryStoreRequest(content="Old content"))
        result = await memory_tools.update(MemoryUpdateRequest(
            id=stored.id, content="New content"
        ))

        assert result.previous_content == "Old content"
        node = await memory_tools.get(MemoryGetRequest(id=stored.id))
        assert node.node.content == "New content"

    @pytest.mark.asyncio
    async def test_update_metadata_merged(self, memory_tools):
        """Metadata update merges with existing keys."""
        from anyide.models import MemoryStoreRequest, MemoryUpdateRequest, MemoryGetRequest

        stored = await memory_tools.store(MemoryStoreRequest(
            content="Node", metadata={"key1": "val1", "key2": "val2"}
        ))
        await memory_tools.update(MemoryUpdateRequest(
            id=stored.id, metadata={"key2": "updated", "key3": "new"}
        ))

        node = await memory_tools.get(MemoryGetRequest(id=stored.id))
        assert node.node.metadata["key1"] == "val1"   # preserved
        assert node.node.metadata["key2"] == "updated"  # updated
        assert node.node.metadata["key3"] == "new"     # added

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, memory_tools):
        """Updating a non-existent node raises NodeNotFoundError."""
        from anyide.models import MemoryUpdateRequest
        from anyide.modules.memory.tools import NodeNotFoundError

        with pytest.raises(NodeNotFoundError):
            await memory_tools.update(MemoryUpdateRequest(id="no-such-id", content="x"))


# ---------------------------------------------------------------------------
# TestMemoryDelete
# ---------------------------------------------------------------------------

class TestMemoryDelete:
    """Tests for memory_delete."""

    @pytest.mark.asyncio
    async def test_delete_node(self, memory_tools):
        """Deleting a node removes it from the graph."""
        from anyide.models import MemoryStoreRequest, MemoryDeleteRequest, MemoryGetRequest
        from anyide.modules.memory.tools import NodeNotFoundError

        stored = await memory_tools.store(MemoryStoreRequest(content="To be deleted"))
        result = await memory_tools.delete(MemoryDeleteRequest(id=stored.id))

        assert result.deleted_node["id"] == stored.id

        with pytest.raises(NodeNotFoundError):
            await memory_tools.get(MemoryGetRequest(id=stored.id))

    @pytest.mark.asyncio
    async def test_delete_counts_edges(self, memory_tools):
        """deleted_edges count reflects actual edges removed."""
        from anyide.models import MemoryStoreRequest, MemoryStoreRelation, MemoryDeleteRequest

        target = await memory_tools.store(MemoryStoreRequest(content="Target"))
        source = await memory_tools.store(MemoryStoreRequest(
            content="Source",
            relations=[MemoryStoreRelation(target_id=target.id, relation="related_to")],
        ))

        result = await memory_tools.delete(MemoryDeleteRequest(id=source.id))
        assert result.deleted_edges >= 1

    @pytest.mark.asyncio
    async def test_delete_lists_orphaned_children(self, memory_tools):
        """Deleting a parent lists orphaned children when cascade=false."""
        from anyide.models import MemoryStoreRequest, MemoryLinkRequest, MemoryDeleteRequest

        parent = await memory_tools.store(MemoryStoreRequest(content="Parent"))
        child = await memory_tools.store(MemoryStoreRequest(content="Child"))
        await memory_tools.link(MemoryLinkRequest(
            source_id=parent.id, target_id=child.id, relation="parent_of"
        ))

        result = await memory_tools.delete(MemoryDeleteRequest(id=parent.id, cascade=False))
        orphan_ids = [o["id"] for o in result.orphaned_children]
        assert child.id in orphan_ids

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, memory_tools):
        """Deleting a non-existent node raises NodeNotFoundError."""
        from anyide.models import MemoryDeleteRequest
        from anyide.modules.memory.tools import NodeNotFoundError

        with pytest.raises(NodeNotFoundError):
            await memory_tools.delete(MemoryDeleteRequest(id="ghost"))


# ---------------------------------------------------------------------------
# TestMemoryLink
# ---------------------------------------------------------------------------

class TestMemoryLink:
    """Tests for memory_link."""

    @pytest.mark.asyncio
    async def test_link_creates_edge(self, memory_tools):
        """Creating a link returns created=True and an edge ID."""
        from anyide.models import MemoryStoreRequest, MemoryLinkRequest

        a = await memory_tools.store(MemoryStoreRequest(content="Node A"))
        b = await memory_tools.store(MemoryStoreRequest(content="Node B"))

        result = await memory_tools.link(MemoryLinkRequest(
            source_id=a.id, target_id=b.id, relation="related_to"
        ))

        assert result.created is True
        assert result.edge["source_id"] == a.id
        assert result.edge["target_id"] == b.id

    @pytest.mark.asyncio
    async def test_link_update_existing_returns_created_false(self, memory_tools):
        """Linking the same pair again returns created=False (update)."""
        from anyide.models import MemoryStoreRequest, MemoryLinkRequest

        a = await memory_tools.store(MemoryStoreRequest(content="A"))
        b = await memory_tools.store(MemoryStoreRequest(content="B"))

        await memory_tools.link(MemoryLinkRequest(
            source_id=a.id, target_id=b.id, relation="depends_on"
        ))
        result = await memory_tools.link(MemoryLinkRequest(
            source_id=a.id, target_id=b.id, relation="depends_on", weight=0.5
        ))

        assert result.created is False

    @pytest.mark.asyncio
    async def test_link_bidirectional_creates_two_edges(self, memory_tools):
        """bidirectional=True creates both directions."""
        from anyide.models import MemoryStoreRequest, MemoryLinkRequest, MemoryGetRequest

        a = await memory_tools.store(MemoryStoreRequest(content="A"))
        b = await memory_tools.store(MemoryStoreRequest(content="B"))

        await memory_tools.link(MemoryLinkRequest(
            source_id=a.id, target_id=b.id, relation="related_to", bidirectional=True
        ))

        # Both nodes should have the relation
        node_a = await memory_tools.get(MemoryGetRequest(id=a.id))
        node_b = await memory_tools.get(MemoryGetRequest(id=b.id))

        a_relations = {r.neighbor["id"] for r in node_a.relations}
        b_relations = {r.neighbor["id"] for r in node_b.relations}

        assert b.id in a_relations
        assert a.id in b_relations

    @pytest.mark.asyncio
    async def test_link_nonexistent_source_raises(self, memory_tools):
        """Linking from a non-existent source raises NodeNotFoundError."""
        from anyide.models import MemoryStoreRequest, MemoryLinkRequest
        from anyide.modules.memory.tools import NodeNotFoundError

        b = await memory_tools.store(MemoryStoreRequest(content="B"))
        with pytest.raises(NodeNotFoundError):
            await memory_tools.link(MemoryLinkRequest(
                source_id="ghost", target_id=b.id, relation="related_to"
            ))


# ---------------------------------------------------------------------------
# TestGraphTraversal
# ---------------------------------------------------------------------------

class TestGraphTraversal:
    """Tests for memory_children, memory_ancestors, memory_roots, memory_related, memory_subtree."""

    @pytest_asyncio.fixture
    async def tree(self, memory_tools):
        """
        Build a simple tree:
            root
            ├── child1
            │   └── grandchild
            └── child2
        All connected via parent_of edges.
        """
        from anyide.models import MemoryStoreRequest, MemoryLinkRequest

        root = await memory_tools.store(MemoryStoreRequest(content="root", name="root"))
        child1 = await memory_tools.store(MemoryStoreRequest(content="child1", name="child1"))
        child2 = await memory_tools.store(MemoryStoreRequest(content="child2", name="child2"))
        gc = await memory_tools.store(MemoryStoreRequest(content="grandchild", name="grandchild"))

        # parent_of: source is parent, target is child
        await memory_tools.link(MemoryLinkRequest(
            source_id=root.id, target_id=child1.id, relation="parent_of"
        ))
        await memory_tools.link(MemoryLinkRequest(
            source_id=root.id, target_id=child2.id, relation="parent_of"
        ))
        await memory_tools.link(MemoryLinkRequest(
            source_id=child1.id, target_id=gc.id, relation="parent_of"
        ))

        return {"root": root, "child1": child1, "child2": child2, "gc": gc}

    @pytest.mark.asyncio
    async def test_children_returns_immediate_children(self, memory_tools, tree):
        """memory_children returns direct children only."""
        from anyide.models import MemoryChildrenRequest

        result = await memory_tools.children(MemoryChildrenRequest(id=tree["root"].id))
        ids = {n.id for n in result.nodes}
        assert tree["child1"].id in ids
        assert tree["child2"].id in ids
        assert tree["gc"].id not in ids
        assert result.total == 2

    @pytest.mark.asyncio
    async def test_ancestors_returns_all_ancestors(self, memory_tools, tree):
        """memory_ancestors returns all ancestors up to max_depth."""
        from anyide.models import MemoryAncestorsRequest

        result = await memory_tools.ancestors(MemoryAncestorsRequest(id=tree["gc"].id))
        ids = {n.id for n in result.nodes}
        assert tree["child1"].id in ids
        assert tree["root"].id in ids
        assert tree["child2"].id not in ids

    @pytest.mark.asyncio
    async def test_roots_returns_nodes_with_no_parent(self, memory_tools, tree):
        """memory_roots returns only the root node in this tree."""
        result = await memory_tools.roots()
        ids = {n.id for n in result.nodes}
        assert tree["root"].id in ids
        assert tree["child1"].id not in ids
        assert tree["gc"].id not in ids

    @pytest.mark.asyncio
    async def test_related_returns_connected_nodes(self, memory_tools, tree):
        """memory_related returns all directly connected nodes (any edge type)."""
        from anyide.models import MemoryRelatedRequest

        result = await memory_tools.related(MemoryRelatedRequest(id=tree["root"].id))
        ids = {n.id for n in result.nodes}
        assert tree["child1"].id in ids
        assert tree["child2"].id in ids

    @pytest.mark.asyncio
    async def test_related_with_relation_filter(self, memory_tools, tree):
        """memory_related with relation filter narrows results."""
        from anyide.models import MemoryRelatedRequest, MemoryStoreRequest, MemoryLinkRequest

        # Add a non-parent_of edge
        sibling = await memory_tools.store(MemoryStoreRequest(content="sibling"))
        await memory_tools.link(MemoryLinkRequest(
            source_id=tree["root"].id, target_id=sibling.id, relation="related_to"
        ))

        result = await memory_tools.related(MemoryRelatedRequest(
            id=tree["root"].id, relation="related_to"
        ))
        ids = {n.id for n in result.nodes}
        assert sibling.id in ids
        assert tree["child1"].id not in ids  # connected by parent_of, not related_to

    @pytest.mark.asyncio
    async def test_subtree_returns_all_descendants(self, memory_tools, tree):
        """memory_subtree returns all descendants excluding the root itself."""
        from anyide.models import MemorySubtreeRequest

        result = await memory_tools.subtree(MemorySubtreeRequest(id=tree["root"].id))
        ids = {n.id for n in result.nodes}
        assert tree["child1"].id in ids
        assert tree["child2"].id in ids
        assert tree["gc"].id in ids
        assert tree["root"].id not in ids  # root not included

    @pytest.mark.asyncio
    async def test_subtree_respects_max_depth(self, memory_tools, tree):
        """subtree with max_depth=1 returns only immediate children."""
        from anyide.models import MemorySubtreeRequest

        result = await memory_tools.subtree(MemorySubtreeRequest(
            id=tree["root"].id, max_depth=1
        ))
        ids = {n.id for n in result.nodes}
        assert tree["child1"].id in ids
        assert tree["child2"].id in ids
        assert tree["gc"].id not in ids  # depth 2 — excluded

    @pytest.mark.asyncio
    async def test_ancestors_depth_limit(self, memory_tools, tree):
        """Ancestors with max_depth=1 returns only immediate parent."""
        from anyide.models import MemoryAncestorsRequest

        result = await memory_tools.ancestors(MemoryAncestorsRequest(
            id=tree["gc"].id, max_depth=1
        ))
        ids = {n.id for n in result.nodes}
        assert tree["child1"].id in ids
        assert tree["root"].id not in ids  # depth 2 — excluded


# ---------------------------------------------------------------------------
# TestMemoryStats
# ---------------------------------------------------------------------------

class TestMemoryStats:
    """Tests for memory_stats."""

    @pytest.mark.asyncio
    async def test_stats_empty_graph(self, memory_tools):
        """Stats on an empty graph returns zeros."""
        result = await memory_tools.stats()

        assert result.total_nodes == 0
        assert result.total_edges == 0
        assert result.orphaned_nodes == 0

    @pytest.mark.asyncio
    async def test_stats_counts_nodes_and_edges(self, memory_tools):
        """Stats reflect actual node and edge counts."""
        from anyide.models import MemoryStoreRequest, MemoryLinkRequest

        a = await memory_tools.store(MemoryStoreRequest(content="A", entity_type="concept"))
        b = await memory_tools.store(MemoryStoreRequest(content="B", entity_type="fact"))
        await memory_tools.link(MemoryLinkRequest(
            source_id=a.id, target_id=b.id, relation="related_to"
        ))

        result = await memory_tools.stats()

        assert result.total_nodes == 2
        assert result.total_edges == 1
        assert result.nodes_by_type.get("concept", 0) >= 1
        assert result.nodes_by_type.get("fact", 0) >= 1
        assert result.edges_by_relation.get("related_to", 0) >= 1

    @pytest.mark.asyncio
    async def test_stats_orphaned_nodes(self, memory_tools):
        """Orphaned node count includes nodes with no edges."""
        from anyide.models import MemoryStoreRequest, MemoryLinkRequest

        await memory_tools.store(MemoryStoreRequest(content="Isolated"))
        connected_a = await memory_tools.store(MemoryStoreRequest(content="A"))
        connected_b = await memory_tools.store(MemoryStoreRequest(content="B"))
        await memory_tools.link(MemoryLinkRequest(
            source_id=connected_a.id, target_id=connected_b.id, relation="related_to"
        ))

        result = await memory_tools.stats()
        assert result.orphaned_nodes == 1  # only `isolated` has no edges

    @pytest.mark.asyncio
    async def test_stats_tags_frequency(self, memory_tools):
        """Tags frequency reflects tag usage across nodes."""
        from anyide.models import MemoryStoreRequest

        await memory_tools.store(MemoryStoreRequest(content="A", tags=["python", "AI"]))
        await memory_tools.store(MemoryStoreRequest(content="B", tags=["python"]))

        result = await memory_tools.stats()
        assert result.tags_frequency.get("python", 0) == 2
        assert result.tags_frequency.get("AI", 0) == 1


# ---------------------------------------------------------------------------
# API endpoint integration tests
# ---------------------------------------------------------------------------

_TEST_SECRETS = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False)
_TEST_SECRETS.write("TOKEN=secret123\n")
_TEST_SECRETS.close()


@pytest.fixture(autouse=True, scope="module")
def setup_memory_app_env():
    """Pin DB_PATH and workspace before any imports touch the app."""
    os.environ["DB_PATH"] = _TEST_DB_PATH
    os.environ["WORKSPACE_BASE_DIR"] = _TEST_WORKSPACE


@pytest_asyncio.fixture
async def app_client():
    """Async test client wired to the FastAPI app with a temp DB."""
    os.environ["DB_PATH"] = _TEST_DB_PATH

    import anyide.config
    import anyide.core.database

    original_load = anyide.config.load_config
    original_db_init = anyide.core.database.Database.__init__

    def patched_load(config_path="config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = _TEST_WORKSPACE
        cfg.secrets.file = _TEST_SECRETS.name
        return cfg

    def patched_db_init(self, db_path=None):
        original_db_init(self, _TEST_DB_PATH)

    anyide.config.load_config = patched_load
    anyide.core.database.Database.__init__ = patched_db_init

    from httpx import AsyncClient, ASGITransport
    from anyide.main import app, db

    await db.connect()

    # Wipe memory tables for test isolation
    conn = db.connection
    await conn.execute("DELETE FROM memory_edges")
    await conn.execute("DELETE FROM memory_nodes")
    await conn.execute("INSERT INTO memory_nodes_fts(memory_nodes_fts) VALUES('rebuild')")
    await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await db.close()
    anyide.config.load_config = original_load
    anyide.core.database.Database.__init__ = original_db_init


@pytest.mark.asyncio
async def test_api_memory_store_and_get(app_client):
    """POST /api/tools/memory/store then /get returns the stored node."""
    store_resp = await app_client.post(
        "/api/tools/memory/store",
        json={"content": "Paris is the capital of France", "tags": ["geography"]},
    )
    assert store_resp.status_code == 200
    store_data = store_resp.json()
    node_id = store_data["id"]
    assert node_id

    get_resp = await app_client.post(
        "/api/tools/memory/get",
        json={"id": node_id},
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["node"]["content"] == "Paris is the capital of France"
    assert get_data["node"]["tags"] == ["geography"]


@pytest.mark.asyncio
async def test_api_memory_search(app_client):
    """POST /api/tools/memory/search returns matching nodes."""
    await app_client.post(
        "/api/tools/memory/store",
        json={"content": "The Eiffel Tower is in Paris"},
    )

    search_resp = await app_client.post(
        "/api/tools/memory/search",
        json={"query": "Eiffel", "search_mode": "fulltext"},
    )
    assert search_resp.status_code == 200
    data = search_resp.json()
    assert data["total_matches"] >= 1
    contents = [r["node"]["content"] for r in data["results"]]
    assert any("Eiffel" in c for c in contents)


@pytest.mark.asyncio
async def test_api_memory_link_and_children(app_client):
    """Linking two nodes via parent_of and querying children works end-to-end."""
    parent_resp = await app_client.post(
        "/api/tools/memory/store", json={"content": "Parent concept"}
    )
    child_resp = await app_client.post(
        "/api/tools/memory/store", json={"content": "Child concept"}
    )
    parent_id = parent_resp.json()["id"]
    child_id = child_resp.json()["id"]

    link_resp = await app_client.post(
        "/api/tools/memory/link",
        json={"source_id": parent_id, "target_id": child_id, "relation": "parent_of"},
    )
    assert link_resp.status_code == 200
    assert link_resp.json()["created"] is True

    children_resp = await app_client.post(
        "/api/tools/memory/children",
        json={"id": parent_id},
    )
    assert children_resp.status_code == 200
    data = children_resp.json()
    child_ids = [n["id"] for n in data["nodes"]]
    assert child_id in child_ids


@pytest.mark.asyncio
async def test_api_memory_stats(app_client):
    """POST /api/tools/memory/stats returns graph statistics."""
    await app_client.post(
        "/api/tools/memory/store", json={"content": "Stats test node"}
    )

    stats_resp = await app_client.post("/api/tools/memory/stats")
    assert stats_resp.status_code == 200
    data = stats_resp.json()
    assert "total_nodes" in data
    assert data["total_nodes"] >= 1


@pytest.mark.asyncio
async def test_api_memory_get_nonexistent_returns_404(app_client):
    """GET for a non-existent node returns 404."""
    resp = await app_client.post(
        "/api/tools/memory/get",
        json={"id": "definitely-does-not-exist"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"] is True
    assert data["error_type"] == "node_not_found"


@pytest.mark.asyncio
async def test_api_memory_update(app_client):
    """POST /api/tools/memory/update changes node content."""
    store_resp = await app_client.post(
        "/api/tools/memory/store", json={"content": "Original content"}
    )
    node_id = store_resp.json()["id"]

    update_resp = await app_client.post(
        "/api/tools/memory/update",
        json={"id": node_id, "content": "Updated content"},
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["previous_content"] == "Original content"

    get_resp = await app_client.post("/api/tools/memory/get", json={"id": node_id})
    assert get_resp.json()["node"]["content"] == "Updated content"


@pytest.mark.asyncio
async def test_api_memory_roots_and_subtree(app_client):
    """Roots and subtree traversal work correctly via the API."""
    root_resp = await app_client.post(
        "/api/tools/memory/store", json={"content": "Root node"}
    )
    child_resp = await app_client.post(
        "/api/tools/memory/store", json={"content": "Child node"}
    )
    root_id = root_resp.json()["id"]
    child_id = child_resp.json()["id"]

    await app_client.post(
        "/api/tools/memory/link",
        json={"source_id": root_id, "target_id": child_id, "relation": "parent_of"},
    )

    roots_resp = await app_client.post("/api/tools/memory/roots")
    assert roots_resp.status_code == 200
    root_ids = [n["id"] for n in roots_resp.json()["nodes"]]
    assert root_id in root_ids

    subtree_resp = await app_client.post(
        "/api/tools/memory/subtree", json={"id": root_id}
    )
    assert subtree_resp.status_code == 200
    subtree_ids = [n["id"] for n in subtree_resp.json()["nodes"]]
    assert child_id in subtree_ids
