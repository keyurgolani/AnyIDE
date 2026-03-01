"""Filesystem module."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.models import (
    FsReadRequest,
    FsReadResponse,
    FsWriteRequest,
    FsWriteResponse,
    FsListRequest,
    FsListResponse,
    FsSearchRequest,
    FsSearchResponse,
)
from anyide.modules.base import ToolModule
from anyide.modules.fs.tools import FilesystemTools


_READ_DESC = """Read the contents of a file at the specified path.

The path is relative to the workspace directory unless an absolute
path within the workspace is provided. Returns the file contents
as text.

Use this tool when you need to:
- Examine file contents before making changes
- Read configuration files
- Inspect source code
- Check log files

Required: path (relative to workspace directory)
Optional: encoding, max_lines (for large files), line_start/line_end (for specific sections)"""

_WRITE_DESC = """Write content to a file at the specified path.

The path is relative to the workspace directory unless an absolute
path within the workspace is provided.

Use this tool when you need to:
- Create new files
- Update existing files
- Append content to files
- Save generated content

Required: path, content
Optional: mode ('create', 'overwrite', 'append'), workspace_dir, create_dirs, encoding

Note: Writing to configuration files (*.conf, *.env, *.yaml, *.yml) requires approval."""

_LIST_DESC = """List contents of a directory.

The path is relative to the workspace directory unless an absolute
path within the workspace is provided.

Use this tool when you need to:
- Browse directory contents
- Find files in a directory
- Explore project structure
- Check if files exist

Optional: path (default: '.'), workspace_dir, recursive, max_depth, include_hidden, pattern

Supports glob patterns like '*.py', 'test_*.txt' for filtering."""

_SEARCH_DESC = """Search for files by name or content.

The path is relative to the workspace directory unless an absolute
path within the workspace is provided.

Use this tool when you need to:
- Find files by name
- Search file contents
- Locate specific code or text
- Discover files matching patterns

Required: query
Optional: path (default: '.'), workspace_dir, search_type ('filename', 'content', 'both'),
         regex, max_results, include_content_preview

Supports both simple text search and regex patterns."""


class FsModule(ToolModule):
    MODULE_NAME = "fs"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Filesystem Tools"

    @property
    def description(self) -> str:
        return "Filesystem operations for AnyIDE"

    @property
    def mcp_tags(self) -> list[str]:
        return ["filesystem"]

    def __init__(self, context):
        super().__init__(context)
        self.fs_tools = FilesystemTools(context.workspace_manager)
        self.context.register_dispatch_target("fs", self.fs_tools)

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/fs/read",
            operation_id="fs_read",
            summary="Read File",
            description=_READ_DESC,
            response_model=FsReadResponse,
            tags=["filesystem"],
        )
        async def fs_read_root(request: FsReadRequest) -> FsReadResponse:
            return await self.context.execute_tool(
                "fs",
                "read",
                request.model_dump(),
                lambda: self.fs_tools.read(request),
            )

        @sub_app.post(
            "/read",
            operation_id="fs_read",
            summary="Read File",
            description=_READ_DESC,
            response_model=FsReadResponse,
            tags=["filesystem"],
        )
        async def fs_read_sub(request: FsReadRequest) -> FsReadResponse:
            return await self.context.execute_tool(
                "fs",
                "read",
                request.model_dump(),
                lambda: self.fs_tools.read(request),
            )

        @app.post(
            "/api/tools/fs/write",
            operation_id="fs_write",
            summary="Write File",
            description=_WRITE_DESC,
            response_model=FsWriteResponse,
            tags=["filesystem"],
        )
        async def fs_write_root(request: FsWriteRequest) -> FsWriteResponse:
            return await self.context.execute_tool(
                "fs",
                "write",
                request.model_dump(),
                lambda: self.fs_tools.write(request),
            )

        @sub_app.post(
            "/write",
            operation_id="fs_write",
            summary="Write File",
            description=_WRITE_DESC,
            response_model=FsWriteResponse,
            tags=["filesystem"],
        )
        async def fs_write_sub(request: FsWriteRequest) -> FsWriteResponse:
            return await self.context.execute_tool(
                "fs",
                "write",
                request.model_dump(),
                lambda: self.fs_tools.write(request),
            )

        @app.post(
            "/api/tools/fs/list",
            operation_id="fs_list",
            summary="List Directory",
            description=_LIST_DESC,
            response_model=FsListResponse,
            tags=["filesystem"],
        )
        async def fs_list_root(request: FsListRequest) -> FsListResponse:
            return await self.context.execute_tool(
                "fs",
                "list",
                request.model_dump(),
                lambda: self.fs_tools.list(request),
            )

        @sub_app.post(
            "/list",
            operation_id="fs_list",
            summary="List Directory",
            description=_LIST_DESC,
            response_model=FsListResponse,
            tags=["filesystem"],
        )
        async def fs_list_sub(request: FsListRequest) -> FsListResponse:
            return await self.context.execute_tool(
                "fs",
                "list",
                request.model_dump(),
                lambda: self.fs_tools.list(request),
            )

        @app.post(
            "/api/tools/fs/search",
            operation_id="fs_search",
            summary="Search Files",
            description=_SEARCH_DESC,
            response_model=FsSearchResponse,
            tags=["filesystem"],
        )
        async def fs_search_root(request: FsSearchRequest) -> FsSearchResponse:
            return await self.context.execute_tool(
                "fs",
                "search",
                request.model_dump(),
                lambda: self.fs_tools.search(request),
            )

        @sub_app.post(
            "/search",
            operation_id="fs_search",
            summary="Search Files",
            description=_SEARCH_DESC,
            response_model=FsSearchResponse,
            tags=["filesystem"],
        )
        async def fs_search_sub(request: FsSearchRequest) -> FsSearchResponse:
            return await self.context.execute_tool(
                "fs",
                "search",
                request.model_dump(),
                lambda: self.fs_tools.search(request),
            )
