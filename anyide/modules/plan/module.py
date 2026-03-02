"""Plan execution module."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.models import (
    PlanCreateRequest,
    PlanCreateResponse,
    PlanExecuteRequest,
    PlanExecuteResponse,
    PlanTaskUpdateRequest,
    PlanTaskUpdateResponse,
    PlanStatusRequest,
    PlanStatusResponse,
    PlanListResponse,
    PlanCancelRequest,
    PlanCancelResponse,
)
from anyide.modules.base import ToolModule
from anyide.modules.plan.tools import PlanTools


_PLAN_CREATE_DESC = """Create a new multi-step plan with a DAG of tasks.

Each task specifies an AnyIDE tool to call (tool_category + tool_name + params).
Tasks may depend on other tasks via `depends_on` (list of task IDs).
Task params may contain `{{task:TASK_ID.field}}` references resolved at runtime.

Validates the DAG at creation time using Kahn's algorithm (cycle detection, missing refs).
Returns the execution order grouped by parallel level.
The response includes `plan_id`; pass that value to `plan_execute`, `plan_update_task`, `plan_status`, and `plan_cancel`.

on_failure policies (plan-level default, overridable per-task):
- **stop**: abort all remaining tasks when any task fails (default)
- **skip_dependents**: skip only tasks that depend on the failed task
- **continue**: continue all tasks regardless of failures"""

_PLAN_EXECUTE_DESC = """Evaluate plan readiness and return runnable tasks.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; if multiple plans share that name, execution fails with an ambiguity error.

This endpoint does not execute tools. It marks a pending plan as running (first call),
computes current `ready_tasks`, and resolves task refs in params using outputs from
already completed tasks.

Use `plan_update_task` after your orchestrator executes each task."""

_PLAN_UPDATE_TASK_DESC = """Update one task status after external execution.

Use this endpoint after your orchestrator runs a ready task:
- set status to `running` when execution starts
- set status to `completed` with `output` when execution succeeds
- set status to `failed` with `error` when execution fails

Failure policies (`stop`, `skip_dependents`, `continue`) are enforced here."""

_PLAN_STATUS_DESC = """Get current status of a plan and all its tasks.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; ambiguous names return an error.

Shows per-task status (pending|running|completed|failed|skipped),
output, error messages, and timing information."""

_PLAN_LIST_DESC = """List all plans with summary information.

Returns plan ID, name, status, task count, and timestamps for all plans."""

_PLAN_CANCEL_DESC = """Cancel a plan, marking all pending and running tasks as skipped.

A cancelled plan cannot be re-executed — create a new plan to re-run.
Useful for aborting long-running plans.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; ambiguous names return an error."""


class PlanModule(ToolModule):
    MODULE_NAME = "plan"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Plan Tools"

    @property
    def description(self) -> str:
        return "DAG-based multi-step plan tracking for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.plan_tools = PlanTools(context.db, context.hitl_manager, context.tool_dispatch)

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/plan/create",
            operation_id="plan_create",
            summary="Create Plan",
            description=_PLAN_CREATE_DESC,
            response_model=PlanCreateResponse,
            tags=["plan"],
        )
        async def plan_create_root(request: PlanCreateRequest) -> PlanCreateResponse:
            return await self.context.execute_tool(
                "plan",
                "create",
                request.model_dump(),
                lambda: self.plan_tools.create(request),
            )

        @sub_app.post(
            "/create",
            operation_id="plan_create",
            summary="Create Plan",
            description=_PLAN_CREATE_DESC,
            response_model=PlanCreateResponse,
            tags=["plan"],
        )
        async def plan_create_sub(request: PlanCreateRequest) -> PlanCreateResponse:
            return await self.context.execute_tool(
                "plan",
                "create",
                request.model_dump(),
                lambda: self.plan_tools.create(request),
            )

        @app.post(
            "/api/tools/plan/execute",
            operation_id="plan_execute",
            summary="Get Ready Tasks",
            description=_PLAN_EXECUTE_DESC,
            response_model=PlanExecuteResponse,
            tags=["plan"],
        )
        async def plan_execute_root(request: PlanExecuteRequest) -> PlanExecuteResponse:
            return await self.context.execute_tool(
                "plan",
                "execute",
                request.model_dump(),
                lambda: self.plan_tools.execute(request),
            )

        @sub_app.post(
            "/execute",
            operation_id="plan_execute",
            summary="Get Ready Tasks",
            description=_PLAN_EXECUTE_DESC,
            response_model=PlanExecuteResponse,
            tags=["plan"],
        )
        async def plan_execute_sub(request: PlanExecuteRequest) -> PlanExecuteResponse:
            return await self.context.execute_tool(
                "plan",
                "execute",
                request.model_dump(),
                lambda: self.plan_tools.execute(request),
            )

        @app.post(
            "/api/tools/plan/update_task",
            operation_id="plan_update_task",
            summary="Update Task Status",
            description=_PLAN_UPDATE_TASK_DESC,
            response_model=PlanTaskUpdateResponse,
            tags=["plan"],
        )
        async def plan_update_task_root(request: PlanTaskUpdateRequest) -> PlanTaskUpdateResponse:
            return await self.context.execute_tool(
                "plan",
                "update_task",
                request.model_dump(),
                lambda: self.plan_tools.update_task(request),
            )

        @sub_app.post(
            "/update_task",
            operation_id="plan_update_task",
            summary="Update Task Status",
            description=_PLAN_UPDATE_TASK_DESC,
            response_model=PlanTaskUpdateResponse,
            tags=["plan"],
        )
        async def plan_update_task_sub(request: PlanTaskUpdateRequest) -> PlanTaskUpdateResponse:
            return await self.context.execute_tool(
                "plan",
                "update_task",
                request.model_dump(),
                lambda: self.plan_tools.update_task(request),
            )

        @app.post(
            "/api/tools/plan/status",
            operation_id="plan_status",
            summary="Get Plan Status",
            description=_PLAN_STATUS_DESC,
            response_model=PlanStatusResponse,
            tags=["plan"],
        )
        async def plan_status_root(request: PlanStatusRequest) -> PlanStatusResponse:
            return await self.context.execute_tool(
                "plan",
                "status",
                request.model_dump(),
                lambda: self.plan_tools.status(request),
            )

        @sub_app.post(
            "/status",
            operation_id="plan_status",
            summary="Get Plan Status",
            description=_PLAN_STATUS_DESC,
            response_model=PlanStatusResponse,
            tags=["plan"],
        )
        async def plan_status_sub(request: PlanStatusRequest) -> PlanStatusResponse:
            return await self.context.execute_tool(
                "plan",
                "status",
                request.model_dump(),
                lambda: self.plan_tools.status(request),
            )

        @app.post(
            "/api/tools/plan/list",
            operation_id="plan_list",
            summary="List Plans",
            description=_PLAN_LIST_DESC,
            response_model=PlanListResponse,
            tags=["plan"],
        )
        async def plan_list_root() -> PlanListResponse:
            return await self.context.execute_tool(
                "plan",
                "list",
                {},
                lambda: self.plan_tools.list(),
            )

        @sub_app.post(
            "/list",
            operation_id="plan_list",
            summary="List Plans",
            description=_PLAN_LIST_DESC,
            response_model=PlanListResponse,
            tags=["plan"],
        )
        async def plan_list_sub() -> PlanListResponse:
            return await self.context.execute_tool(
                "plan",
                "list",
                {},
                lambda: self.plan_tools.list(),
            )

        @app.post(
            "/api/tools/plan/cancel",
            operation_id="plan_cancel",
            summary="Cancel Plan",
            description=_PLAN_CANCEL_DESC,
            response_model=PlanCancelResponse,
            tags=["plan"],
        )
        async def plan_cancel_root(request: PlanCancelRequest) -> PlanCancelResponse:
            return await self.context.execute_tool(
                "plan",
                "cancel",
                request.model_dump(),
                lambda: self.plan_tools.cancel(request),
            )

        @sub_app.post(
            "/cancel",
            operation_id="plan_cancel",
            summary="Cancel Plan",
            description=_PLAN_CANCEL_DESC,
            response_model=PlanCancelResponse,
            tags=["plan"],
        )
        async def plan_cancel_sub(request: PlanCancelRequest) -> PlanCancelResponse:
            return await self.context.execute_tool(
                "plan",
                "cancel",
                request.model_dump(),
                lambda: self.plan_tools.cancel(request),
            )
