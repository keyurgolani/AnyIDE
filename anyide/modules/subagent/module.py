"""Subagent module registration."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.modules.base import ToolModule
from anyide.modules.subagent.schemas import (
    SubagentListResponse,
    SubagentRunRequest,
    SubagentRunResponse,
)
from anyide.modules.subagent.tools import SubagentTools


_LIST_DESC = """List configured subagent types from `config.subagents.types`.

Use this before `subagent_run` to discover valid type IDs and endpoint/model bindings."""

_RUN_DESC = """Run one configured subagent task as a single LLM completion.

Execution flow:
1. Load subagent type config
2. Read and render system prompt template
3. Call unified LLM client with configured endpoint/model defaults
4. Return response plus metadata (latency/usage/model/endpoint)

`override_model` and `override_temperature` are only accepted when enabled for that subagent type."""


class SubagentModule(ToolModule):
    """Config-driven subagent execution tools."""

    MODULE_NAME = "subagent"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Subagent Tools"

    @property
    def description(self) -> str:
        return "Config-driven single-turn specialist subagents powered by AnyIDE LLM endpoints"

    def __init__(self, context):
        super().__init__(context)
        self.subagent_tools = SubagentTools(
            subagents_config=context.config.subagents,
            llm_client=context.llm_client,
        )
        self.context.register_dispatch_target("subagent", self.subagent_tools)

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/subagent/list",
            operation_id="subagent_list",
            summary="List Subagent Types",
            description=_LIST_DESC,
            response_model=SubagentListResponse,
            tags=["subagent"],
        )
        async def subagent_list_root() -> SubagentListResponse:
            return await self.context.execute_tool(
                "subagent",
                "list",
                {},
                lambda: self.subagent_tools.list(),
            )

        @sub_app.post(
            "/list",
            operation_id="subagent_list",
            summary="List Subagent Types",
            description=_LIST_DESC,
            response_model=SubagentListResponse,
            tags=["subagent"],
        )
        async def subagent_list_sub() -> SubagentListResponse:
            return await self.context.execute_tool(
                "subagent",
                "list",
                {},
                lambda: self.subagent_tools.list(),
            )

        @app.post(
            "/api/tools/subagent/run",
            operation_id="subagent_run",
            summary="Run Subagent",
            description=_RUN_DESC,
            response_model=SubagentRunResponse,
            tags=["subagent"],
        )
        async def subagent_run_root(request: SubagentRunRequest) -> SubagentRunResponse:
            return await self.context.execute_tool(
                "subagent",
                "run",
                request.model_dump(),
                lambda: self.subagent_tools.run(request),
            )

        @sub_app.post(
            "/run",
            operation_id="subagent_run",
            summary="Run Subagent",
            description=_RUN_DESC,
            response_model=SubagentRunResponse,
            tags=["subagent"],
        )
        async def subagent_run_sub(request: SubagentRunRequest) -> SubagentRunResponse:
            return await self.context.execute_tool(
                "subagent",
                "run",
                request.model_dump(),
                lambda: self.subagent_tools.run(request),
            )
