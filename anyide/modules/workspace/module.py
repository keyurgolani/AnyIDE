"""Workspace module."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.models import WorkspaceInfoResponse, WorkspaceSecretsListResponse
from anyide.modules.base import ToolModule
from anyide.modules.workspace.tools import WorkspaceTools


_INFO_DESC = """Get information about the workspace configuration.

Returns the default workspace directory, available paths, disk usage,
and available tool categories.

Use this tool when you need to:
- Understand the workspace boundaries
- Check available disk space
- See what tool categories are available
- Get the base workspace path for other operations

No parameters required."""

_SECRETS_DESC = """List the names (keys) of all configured secrets.

Secret VALUES are never exposed — only their names are returned so you
know which keys are available for use as {{secret:KEY}} templates in
tool parameters (headers, environment variables, etc.).

Use this tool to:
- Discover available secret keys before using them in requests
- Verify that a required secret is configured

No parameters required."""


class _WorkspaceDispatch:
    """Plan-dispatch wrapper for workspace tools."""

    def __init__(self, module: "WorkspaceModule"):
        self._module = module

    async def info(self) -> WorkspaceInfoResponse:
        return await self._module.workspace_tools.info()

    async def secrets_list(self) -> WorkspaceSecretsListResponse:
        return await self._module._workspace_secrets_list()


class WorkspaceModule(ToolModule):
    MODULE_NAME = "workspace"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Workspace Tools"

    @property
    def description(self) -> str:
        return "Workspace management for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.workspace_tools = WorkspaceTools(
            context.workspace_manager,
            context.secret_manager,
            tool_categories_provider=lambda: list(context.enabled_modules) or [
                "fs",
                "workspace",
                "shell",
                "git",
                "docker",
                "http",
                "memory",
                "plan",
            ],
        )
        self._dispatch = _WorkspaceDispatch(self)
        self.context.register_dispatch_target("workspace", self._dispatch)

    async def _workspace_secrets_list(self) -> WorkspaceSecretsListResponse:
        keys = self.context.secret_manager.list_keys()
        return WorkspaceSecretsListResponse(
            keys=keys,
            count=len(keys),
            secrets_file=str(self.context.secret_manager.secrets_file),
        )

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/workspace/info",
            operation_id="workspace_info",
            summary="Get Workspace Information",
            description=_INFO_DESC,
            response_model=WorkspaceInfoResponse,
            tags=["workspace"],
        )
        async def workspace_info_root() -> WorkspaceInfoResponse:
            return await self.context.execute_tool(
                "workspace",
                "info",
                {},
                lambda: self.workspace_tools.info(),
            )

        @sub_app.post(
            "/info",
            operation_id="workspace_info",
            summary="Get Workspace Information",
            description=_INFO_DESC,
            response_model=WorkspaceInfoResponse,
            tags=["workspace"],
        )
        async def workspace_info_sub() -> WorkspaceInfoResponse:
            return await self.context.execute_tool(
                "workspace",
                "info",
                {},
                lambda: self.workspace_tools.info(),
            )

        @app.post(
            "/api/tools/workspace/secrets/list",
            operation_id="workspace_secrets_list",
            summary="List Configured Secrets",
            description=_SECRETS_DESC,
            response_model=WorkspaceSecretsListResponse,
            tags=["workspace"],
        )
        async def workspace_secrets_list_root() -> WorkspaceSecretsListResponse:
            return await self.context.execute_tool(
                "workspace",
                "secrets_list",
                {},
                lambda: self._workspace_secrets_list(),
            )

        @sub_app.post(
            "/secrets/list",
            operation_id="workspace_secrets_list",
            summary="List Configured Secrets",
            description=_SECRETS_DESC,
            response_model=WorkspaceSecretsListResponse,
            tags=["workspace"],
        )
        async def workspace_secrets_list_sub() -> WorkspaceSecretsListResponse:
            return await self.context.execute_tool(
                "workspace",
                "secrets_list",
                {},
                lambda: self._workspace_secrets_list(),
            )
