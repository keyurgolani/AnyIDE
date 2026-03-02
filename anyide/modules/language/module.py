"""Language tools module registration."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.modules.base import ToolModule
from anyide.modules.language.schemas import (
    LangApplyPatchRequest,
    LangApplyPatchResponse,
    LangCreateFileRequest,
    LangCreateFileResponse,
    LangDiffRequest,
    LangDiffResponse,
    LangIndexRequest,
    LangIndexResponse,
    LangReadFileRequest,
    LangReadFileResponse,
    LangReferenceGraphRequest,
    LangReferenceGraphResponse,
    LangSearchSymbolsRequest,
    LangSearchSymbolsResponse,
    LangSkeletonRequest,
    LangSkeletonResponse,
    LangValidateRequest,
    LangValidateResponse,
)
from anyide.modules.language.tools import LanguageTools


class LanguageModule(ToolModule):
    """Tree-sitter-based language intelligence tools."""

    MODULE_NAME = "language"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Language Tools"

    @property
    def description(self) -> str:
        return "Structure-aware code read/edit/index/validate tooling for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.language_tools = LanguageTools(
            workspace=context.workspace_manager,
            db=context.db,
            config=context.config,
        )
        self.context.register_dispatch_target("language", self.language_tools)

    def on_startup(self) -> None:
        self.language_tools.on_startup()

    async def on_shutdown(self) -> None:
        await self.language_tools.on_shutdown()

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        self._register_read_file(app, sub_app)
        self._register_skeleton(app, sub_app)
        self._register_diff(app, sub_app)
        self._register_apply_patch(app, sub_app)
        self._register_create_file(app, sub_app)
        self._register_index(app, sub_app)
        self._register_search_symbols(app, sub_app)
        self._register_reference_graph(app, sub_app)
        self._register_validate(app, sub_app)

    def _register_read_file(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/read_file",
            operation_id="lang_read_file",
            summary="Read File with Structure Awareness",
            response_model=LangReadFileResponse,
            tags=["language"],
        )
        async def lang_read_file_root(request: LangReadFileRequest) -> LangReadFileResponse:
            return await self.context.execute_tool(
                "language",
                "read_file",
                request.model_dump(),
                lambda: self.language_tools.read_file(request),
            )

        @sub_app.post(
            "/read_file",
            operation_id="lang_read_file",
            summary="Read File with Structure Awareness",
            response_model=LangReadFileResponse,
            tags=["language"],
        )
        async def lang_read_file_sub(request: LangReadFileRequest) -> LangReadFileResponse:
            return await self.context.execute_tool(
                "language",
                "read_file",
                request.model_dump(),
                lambda: self.language_tools.read_file(request),
            )

    def _register_skeleton(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/skeleton",
            operation_id="lang_skeleton",
            summary="Get File Skeleton",
            response_model=LangSkeletonResponse,
            tags=["language"],
        )
        async def lang_skeleton_root(request: LangSkeletonRequest) -> LangSkeletonResponse:
            return await self.context.execute_tool(
                "language",
                "skeleton",
                request.model_dump(),
                lambda: self.language_tools.skeleton(request),
            )

        @sub_app.post(
            "/skeleton",
            operation_id="lang_skeleton",
            summary="Get File Skeleton",
            response_model=LangSkeletonResponse,
            tags=["language"],
        )
        async def lang_skeleton_sub(request: LangSkeletonRequest) -> LangSkeletonResponse:
            return await self.context.execute_tool(
                "language",
                "skeleton",
                request.model_dump(),
                lambda: self.language_tools.skeleton(request),
            )

    def _register_diff(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/diff",
            operation_id="lang_diff",
            summary="Create Language-Aware Diff",
            response_model=LangDiffResponse,
            tags=["language"],
        )
        async def lang_diff_root(request: LangDiffRequest) -> LangDiffResponse:
            return await self.context.execute_tool(
                "language",
                "diff",
                request.model_dump(),
                lambda: self.language_tools.diff(request),
            )

        @sub_app.post(
            "/diff",
            operation_id="lang_diff",
            summary="Create Language-Aware Diff",
            response_model=LangDiffResponse,
            tags=["language"],
        )
        async def lang_diff_sub(request: LangDiffRequest) -> LangDiffResponse:
            return await self.context.execute_tool(
                "language",
                "diff",
                request.model_dump(),
                lambda: self.language_tools.diff(request),
            )

    def _register_apply_patch(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/apply_patch",
            operation_id="lang_apply_patch",
            summary="Apply Function-Anchored Patch",
            response_model=LangApplyPatchResponse,
            tags=["language"],
        )
        async def lang_apply_patch_root(
            request: LangApplyPatchRequest,
        ) -> LangApplyPatchResponse:
            return await self.context.execute_tool(
                "language",
                "apply_patch",
                request.model_dump(),
                lambda: self.language_tools.apply_patch(request),
            )

        @sub_app.post(
            "/apply_patch",
            operation_id="lang_apply_patch",
            summary="Apply Function-Anchored Patch",
            response_model=LangApplyPatchResponse,
            tags=["language"],
        )
        async def lang_apply_patch_sub(request: LangApplyPatchRequest) -> LangApplyPatchResponse:
            return await self.context.execute_tool(
                "language",
                "apply_patch",
                request.model_dump(),
                lambda: self.language_tools.apply_patch(request),
            )

    def _register_create_file(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/create_file",
            operation_id="lang_create_file",
            summary="Create Code File with Validation",
            response_model=LangCreateFileResponse,
            tags=["language"],
        )
        async def lang_create_file_root(
            request: LangCreateFileRequest,
        ) -> LangCreateFileResponse:
            return await self.context.execute_tool(
                "language",
                "create_file",
                request.model_dump(),
                lambda: self.language_tools.create_file(request),
            )

        @sub_app.post(
            "/create_file",
            operation_id="lang_create_file",
            summary="Create Code File with Validation",
            response_model=LangCreateFileResponse,
            tags=["language"],
        )
        async def lang_create_file_sub(request: LangCreateFileRequest) -> LangCreateFileResponse:
            return await self.context.execute_tool(
                "language",
                "create_file",
                request.model_dump(),
                lambda: self.language_tools.create_file(request),
            )

    def _register_index(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/index",
            operation_id="lang_index",
            summary="Index Workspace Symbols",
            response_model=LangIndexResponse,
            tags=["language"],
        )
        async def lang_index_root(request: LangIndexRequest) -> LangIndexResponse:
            return await self.context.execute_tool(
                "language",
                "index",
                request.model_dump(),
                lambda: self.language_tools.index(request),
            )

        @sub_app.post(
            "/index",
            operation_id="lang_index",
            summary="Index Workspace Symbols",
            response_model=LangIndexResponse,
            tags=["language"],
        )
        async def lang_index_sub(request: LangIndexRequest) -> LangIndexResponse:
            return await self.context.execute_tool(
                "language",
                "index",
                request.model_dump(),
                lambda: self.language_tools.index(request),
            )

    def _register_search_symbols(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/search_symbols",
            operation_id="lang_search_symbols",
            summary="Search Indexed Symbols",
            response_model=LangSearchSymbolsResponse,
            tags=["language"],
        )
        async def lang_search_symbols_root(
            request: LangSearchSymbolsRequest,
        ) -> LangSearchSymbolsResponse:
            return await self.context.execute_tool(
                "language",
                "search_symbols",
                request.model_dump(),
                lambda: self.language_tools.search_symbols(request),
            )

        @sub_app.post(
            "/search_symbols",
            operation_id="lang_search_symbols",
            summary="Search Indexed Symbols",
            response_model=LangSearchSymbolsResponse,
            tags=["language"],
        )
        async def lang_search_symbols_sub(
            request: LangSearchSymbolsRequest,
        ) -> LangSearchSymbolsResponse:
            return await self.context.execute_tool(
                "language",
                "search_symbols",
                request.model_dump(),
                lambda: self.language_tools.search_symbols(request),
            )

    def _register_reference_graph(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/reference_graph",
            operation_id="lang_reference_graph",
            summary="Build Function Reference Graph",
            response_model=LangReferenceGraphResponse,
            tags=["language"],
        )
        async def lang_reference_graph_root(
            request: LangReferenceGraphRequest,
        ) -> LangReferenceGraphResponse:
            return await self.context.execute_tool(
                "language",
                "reference_graph",
                request.model_dump(),
                lambda: self.language_tools.reference_graph(request),
            )

        @sub_app.post(
            "/reference_graph",
            operation_id="lang_reference_graph",
            summary="Build Function Reference Graph",
            response_model=LangReferenceGraphResponse,
            tags=["language"],
        )
        async def lang_reference_graph_sub(
            request: LangReferenceGraphRequest,
        ) -> LangReferenceGraphResponse:
            return await self.context.execute_tool(
                "language",
                "reference_graph",
                request.model_dump(),
                lambda: self.language_tools.reference_graph(request),
            )

    def _register_validate(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/language/validate",
            operation_id="lang_validate",
            summary="Validate Syntax and Linting",
            response_model=LangValidateResponse,
            tags=["language"],
        )
        async def lang_validate_root(request: LangValidateRequest) -> LangValidateResponse:
            return await self.context.execute_tool(
                "language",
                "validate",
                request.model_dump(),
                lambda: self.language_tools.validate(request),
            )

        @sub_app.post(
            "/validate",
            operation_id="lang_validate",
            summary="Validate Syntax and Linting",
            response_model=LangValidateResponse,
            tags=["language"],
        )
        async def lang_validate_sub(request: LangValidateRequest) -> LangValidateResponse:
            return await self.context.execute_tool(
                "language",
                "validate",
                request.model_dump(),
                lambda: self.language_tools.validate(request),
            )
