"""Memory graph tools module."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.models import (
    MemoryStoreRequest,
    MemoryStoreResponse,
    MemoryGetRequest,
    MemoryGetResponse,
    MemorySearchRequest,
    MemorySearchResponse,
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
from anyide.modules.base import ToolModule
from anyide.modules.memory.tools import MemoryTools


_MEMORY_STORE_DESC = """Store a piece of knowledge as a node in the knowledge graph.

Each node holds an atomic fact, concept, or piece of information. Optionally
create edges to existing nodes in the same request.

Required: content
Optional: name (defaults to first 60 chars), entity_type (concept/fact/task/person/event/note),
          tags (list of strings), metadata (dict), source, relations (list of {target_id, relation, weight})

Entity types:
- concept: Abstract idea or category
- fact: Objective, verifiable statement
- task: An action item or TODO
- person: A person or agent
- event: Something that happened or will happen
- note: Free-form note or observation"""

_MEMORY_GET_DESC = """Retrieve a memory node by its ID along with its relationships.

Returns the full node content and metadata, plus connected edges and neighbor summaries.

Required: id
Optional: include_relations (default: true), depth (default: 1 — immediate neighbors only)"""

_MEMORY_SEARCH_DESC = """Search the knowledge graph using full-text search and/or tag filtering.

Three search modes:
- fulltext: FTS5 BM25 full-text search on name, content, and tags (best for keyword queries)
- tags: Filter by exact tag values (best for category lookups)
- hybrid: Full-text + tag filter combined (default, most flexible)

Required: query
Optional: entity_type, tags, max_results (default: 10), search_mode, temporal_filter (ISO date)"""

_MEMORY_UPDATE_DESC = """Update a memory node's content or metadata.

Only provided fields are changed. Metadata is merged (patch semantics — existing keys preserved).
Tags replace the existing tag list entirely when provided.

Required: id
Optional: content, name, tags, metadata"""

_MEMORY_DELETE_DESC = """Delete a memory node and all its edges.

With cascade=false (default), lists nodes that would become orphaned (their only parent was this node)
but does not delete them. With cascade=true, also deletes those orphaned children.

IMPORTANT: This operation requires human approval by default.

Required: id
Optional: cascade (default: false)"""

_MEMORY_LINK_DESC = """Create or update a directed relationship between two nodes.

If an edge with the same source, target, and relation already exists, updates its weight and metadata.

Common relation types: related_to, depends_on, parent_of, contradicts, supersedes, derived_from

Required: source_id, target_id, relation
Optional: weight (default: 1.0), bidirectional (default: false), metadata, valid_from, valid_until"""

_MEMORY_CHILDREN_DESC = """Get the immediate child nodes connected via parent_of edges.

In the graph, "A parent_of B" means A→B where A is the parent.
This tool returns all B where A→B with relation='parent_of'.

Required: id"""

_MEMORY_ANCESTORS_DESC = """Traverse parent_of edges upward to find all ancestor nodes (recursive CTE).

Walks the graph from the given node toward root nodes by following parent_of edges in reverse.
Stops when max_depth is reached or no more ancestors exist.

Required: id
Optional: max_depth (default: 10)"""

_MEMORY_ROOTS_DESC = """Get all root nodes — nodes that have no incoming parent_of edges.

Root nodes are the top-level entries in the hierarchy: nothing is their parent."""

_MEMORY_RELATED_DESC = """Get all nodes connected to the given node by any edge type (or a specific type).

Traverses both outgoing and incoming edges (bidirectional single-hop).

Required: id
Optional: relation (filter to a specific relation type)"""

_MEMORY_SUBTREE_DESC = """Return the full subtree rooted at the given node using a recursive CTE.

Follows parent_of edges downward (from parent to children, then grandchildren, etc.).
The root node itself is NOT included in the results.

Required: id
Optional: max_depth (default: 10)"""

_MEMORY_STATS_DESC = """Return knowledge graph statistics and metrics.

Provides an overview of the entire graph: node/edge counts, type breakdown,
most connected nodes, orphaned nodes, recent activity, and tag frequency."""


class MemoryModule(ToolModule):
    MODULE_NAME = "memory"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Memory Tools"

    @property
    def description(self) -> str:
        return "Graph-based knowledge storage for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.memory_tools = MemoryTools(context.db)
        self.context.register_dispatch_target("memory", self.memory_tools)

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/memory/store",
            operation_id="memory_store",
            summary="Store Knowledge Node",
            description=_MEMORY_STORE_DESC,
            response_model=MemoryStoreResponse,
            tags=["memory"],
        )
        async def memory_store_root(request: MemoryStoreRequest) -> MemoryStoreResponse:
            return await self.context.execute_tool(
                "memory",
                "store",
                request.model_dump(),
                lambda: self.memory_tools.store(request),
            )

        @sub_app.post(
            "/store",
            operation_id="memory_store",
            summary="Store Knowledge Node",
            description=_MEMORY_STORE_DESC,
            response_model=MemoryStoreResponse,
            tags=["memory"],
        )
        async def memory_store_sub(request: MemoryStoreRequest) -> MemoryStoreResponse:
            return await self.context.execute_tool(
                "memory",
                "store",
                request.model_dump(),
                lambda: self.memory_tools.store(request),
            )

        @app.post(
            "/api/tools/memory/get",
            operation_id="memory_get",
            summary="Retrieve Knowledge Node",
            description=_MEMORY_GET_DESC,
            response_model=MemoryGetResponse,
            tags=["memory"],
        )
        async def memory_get_root(request: MemoryGetRequest) -> MemoryGetResponse:
            return await self.context.execute_tool(
                "memory",
                "get",
                request.model_dump(),
                lambda: self.memory_tools.get(request),
            )

        @sub_app.post(
            "/get",
            operation_id="memory_get",
            summary="Retrieve Knowledge Node",
            description=_MEMORY_GET_DESC,
            response_model=MemoryGetResponse,
            tags=["memory"],
        )
        async def memory_get_sub(request: MemoryGetRequest) -> MemoryGetResponse:
            return await self.context.execute_tool(
                "memory",
                "get",
                request.model_dump(),
                lambda: self.memory_tools.get(request),
            )

        @app.post(
            "/api/tools/memory/search",
            operation_id="memory_search",
            summary="Search Knowledge Graph",
            description=_MEMORY_SEARCH_DESC,
            response_model=MemorySearchResponse,
            tags=["memory"],
        )
        async def memory_search_root(request: MemorySearchRequest) -> MemorySearchResponse:
            return await self.context.execute_tool(
                "memory",
                "search",
                request.model_dump(),
                lambda: self.memory_tools.search(request),
            )

        @sub_app.post(
            "/search",
            operation_id="memory_search",
            summary="Search Knowledge Graph",
            description=_MEMORY_SEARCH_DESC,
            response_model=MemorySearchResponse,
            tags=["memory"],
        )
        async def memory_search_sub(request: MemorySearchRequest) -> MemorySearchResponse:
            return await self.context.execute_tool(
                "memory",
                "search",
                request.model_dump(),
                lambda: self.memory_tools.search(request),
            )

        @app.post(
            "/api/tools/memory/update",
            operation_id="memory_update",
            summary="Update Knowledge Node",
            description=_MEMORY_UPDATE_DESC,
            response_model=MemoryUpdateResponse,
            tags=["memory"],
        )
        async def memory_update_root(request: MemoryUpdateRequest) -> MemoryUpdateResponse:
            return await self.context.execute_tool(
                "memory",
                "update",
                request.model_dump(),
                lambda: self.memory_tools.update(request),
            )

        @sub_app.post(
            "/update",
            operation_id="memory_update",
            summary="Update Knowledge Node",
            description=_MEMORY_UPDATE_DESC,
            response_model=MemoryUpdateResponse,
            tags=["memory"],
        )
        async def memory_update_sub(request: MemoryUpdateRequest) -> MemoryUpdateResponse:
            return await self.context.execute_tool(
                "memory",
                "update",
                request.model_dump(),
                lambda: self.memory_tools.update(request),
            )

        @app.post(
            "/api/tools/memory/delete",
            operation_id="memory_delete",
            summary="Delete Knowledge Node",
            description=_MEMORY_DELETE_DESC,
            response_model=MemoryDeleteResponse,
            tags=["memory"],
        )
        async def memory_delete_root(request: MemoryDeleteRequest) -> MemoryDeleteResponse:
            return await self.context.execute_tool(
                "memory",
                "delete",
                request.model_dump(),
                lambda: self.memory_tools.delete(request),
                force_hitl=True,
                hitl_reason=f"Deleting memory node '{request.id}' requires approval",
            )

        @sub_app.post(
            "/delete",
            operation_id="memory_delete",
            summary="Delete Knowledge Node",
            description=_MEMORY_DELETE_DESC,
            response_model=MemoryDeleteResponse,
            tags=["memory"],
        )
        async def memory_delete_sub(request: MemoryDeleteRequest) -> MemoryDeleteResponse:
            return await self.context.execute_tool(
                "memory",
                "delete",
                request.model_dump(),
                lambda: self.memory_tools.delete(request),
                force_hitl=True,
                hitl_reason=f"Deleting memory node '{request.id}' requires approval",
            )

        @app.post(
            "/api/tools/memory/link",
            operation_id="memory_link",
            summary="Create Knowledge Relationship",
            description=_MEMORY_LINK_DESC,
            response_model=MemoryLinkResponse,
            tags=["memory"],
        )
        async def memory_link_root(request: MemoryLinkRequest) -> MemoryLinkResponse:
            return await self.context.execute_tool(
                "memory",
                "link",
                request.model_dump(),
                lambda: self.memory_tools.link(request),
            )

        @sub_app.post(
            "/link",
            operation_id="memory_link",
            summary="Create Knowledge Relationship",
            description=_MEMORY_LINK_DESC,
            response_model=MemoryLinkResponse,
            tags=["memory"],
        )
        async def memory_link_sub(request: MemoryLinkRequest) -> MemoryLinkResponse:
            return await self.context.execute_tool(
                "memory",
                "link",
                request.model_dump(),
                lambda: self.memory_tools.link(request),
            )

        @app.post(
            "/api/tools/memory/children",
            operation_id="memory_children",
            summary="Get Child Nodes",
            description=_MEMORY_CHILDREN_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_children_root(
            request: MemoryChildrenRequest,
        ) -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "children",
                request.model_dump(),
                lambda: self.memory_tools.children(request),
            )

        @sub_app.post(
            "/children",
            operation_id="memory_children",
            summary="Get Child Nodes",
            description=_MEMORY_CHILDREN_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_children_sub(
            request: MemoryChildrenRequest,
        ) -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "children",
                request.model_dump(),
                lambda: self.memory_tools.children(request),
            )

        @app.post(
            "/api/tools/memory/ancestors",
            operation_id="memory_ancestors",
            summary="Get Ancestor Nodes",
            description=_MEMORY_ANCESTORS_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_ancestors_root(
            request: MemoryAncestorsRequest,
        ) -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "ancestors",
                request.model_dump(),
                lambda: self.memory_tools.ancestors(request),
            )

        @sub_app.post(
            "/ancestors",
            operation_id="memory_ancestors",
            summary="Get Ancestor Nodes",
            description=_MEMORY_ANCESTORS_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_ancestors_sub(
            request: MemoryAncestorsRequest,
        ) -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "ancestors",
                request.model_dump(),
                lambda: self.memory_tools.ancestors(request),
            )

        @app.post(
            "/api/tools/memory/roots",
            operation_id="memory_roots",
            summary="Get Root Nodes",
            description=_MEMORY_ROOTS_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_roots_root() -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "roots",
                {},
                lambda: self.memory_tools.roots(),
            )

        @sub_app.post(
            "/roots",
            operation_id="memory_roots",
            summary="Get Root Nodes",
            description=_MEMORY_ROOTS_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_roots_sub() -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "roots",
                {},
                lambda: self.memory_tools.roots(),
            )

        @app.post(
            "/api/tools/memory/related",
            operation_id="memory_related",
            summary="Get Related Nodes",
            description=_MEMORY_RELATED_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_related_root(request: MemoryRelatedRequest) -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "related",
                request.model_dump(),
                lambda: self.memory_tools.related(request),
            )

        @sub_app.post(
            "/related",
            operation_id="memory_related",
            summary="Get Related Nodes",
            description=_MEMORY_RELATED_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_related_sub(request: MemoryRelatedRequest) -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "related",
                request.model_dump(),
                lambda: self.memory_tools.related(request),
            )

        @app.post(
            "/api/tools/memory/subtree",
            operation_id="memory_subtree",
            summary="Get Node Subtree",
            description=_MEMORY_SUBTREE_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_subtree_root(request: MemorySubtreeRequest) -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "subtree",
                request.model_dump(),
                lambda: self.memory_tools.subtree(request),
            )

        @sub_app.post(
            "/subtree",
            operation_id="memory_subtree",
            summary="Get Node Subtree",
            description=_MEMORY_SUBTREE_DESC,
            response_model=MemoryNodesResponse,
            tags=["memory"],
        )
        async def memory_subtree_sub(request: MemorySubtreeRequest) -> MemoryNodesResponse:
            return await self.context.execute_tool(
                "memory",
                "subtree",
                request.model_dump(),
                lambda: self.memory_tools.subtree(request),
            )

        @app.post(
            "/api/tools/memory/stats",
            operation_id="memory_stats",
            summary="Knowledge Graph Statistics",
            description=_MEMORY_STATS_DESC,
            response_model=MemoryStatsResponse,
            tags=["memory"],
        )
        async def memory_stats_root() -> MemoryStatsResponse:
            return await self.context.execute_tool(
                "memory",
                "stats",
                {},
                lambda: self.memory_tools.stats(),
            )

        @sub_app.post(
            "/stats",
            operation_id="memory_stats",
            summary="Knowledge Graph Statistics",
            description=_MEMORY_STATS_DESC,
            response_model=MemoryStatsResponse,
            tags=["memory"],
        )
        async def memory_stats_sub() -> MemoryStatsResponse:
            return await self.context.execute_tool(
                "memory",
                "stats",
                {},
                lambda: self.memory_tools.stats(),
            )
