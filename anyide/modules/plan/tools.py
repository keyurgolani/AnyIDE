"""Plan tools — DAG-based multi-step plan creation and execution."""

import asyncio
import json
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from anyide.core.database import Database
from anyide.logging_config import get_logger
from anyide.models import (
    PlanCreateRequest,
    PlanCreateResponse,
    PlanExecuteRequest,
    PlanExecuteResponse,
    PlanStatusRequest,
    PlanStatusResponse,
    PlanTaskStatus,
    PlanListItem,
    PlanListResponse,
    PlanCancelRequest,
    PlanCancelResponse,
)

logger = get_logger(__name__)


class PlanNotFoundError(ValueError):
    """Raised when a requested plan does not exist."""


class PlanValidationError(ValueError):
    """Raised when a plan fails DAG validation (cycle, missing dependency, duplicate IDs)."""


_TASK_REF_PATTERN = re.compile(r"\{\{task:([^.}\s]+)\.([^}\s]+)\}\}")


def _new_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_json_field(value: Optional[str], default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _compute_execution_levels(tasks: List[Dict]) -> List[List[str]]:
    """Kahn's topological sort — returns ordered execution levels.

    Each level contains task IDs that can execute concurrently (all their
    dependencies are in earlier levels).

    Raises:
        PlanValidationError: If cycle detected or a depends_on ID is unknown.
    """
    task_ids: Set[str] = {t["id"] for t in tasks}

    # Validate all depends_on references exist in this plan
    for task in tasks:
        for dep in task.get("depends_on", []):
            if dep not in task_ids:
                raise PlanValidationError(
                    f"Task '{task['id']}' depends on unknown task '{dep}'"
                )

    # in_degree[tid] = number of unsatisfied dependencies
    in_degree: Dict[str, int] = {t["id"]: 0 for t in tasks}
    # adj[tid] = list of task IDs that depend on tid (reverse edges)
    adj: Dict[str, List[str]] = {t["id"]: [] for t in tasks}

    for task in tasks:
        for dep in task.get("depends_on", []):
            in_degree[task["id"]] += 1
            adj[dep].append(task["id"])

    # Start with tasks that have no dependencies
    queue: List[str] = sorted(tid for tid in task_ids if in_degree[tid] == 0)
    levels: List[List[str]] = []
    visited = 0

    while queue:
        levels.append(list(queue))
        next_queue: List[str] = []
        for tid in queue:
            visited += 1
            for neighbor in adj[tid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    next_queue.append(neighbor)
        queue = sorted(next_queue)

    if visited != len(tasks):
        raise PlanValidationError(
            "Cycle detected in task dependency graph — plan cannot be executed"
        )

    return levels


def _get_transitive_dependents(failed_id: str, all_tasks: List[Dict]) -> Set[str]:
    """Return the set of task IDs that transitively depend on failed_id."""
    depends_on_map: Dict[str, List[str]] = {
        t["id"]: _parse_json_field(t.get("depends_on", "[]"), [])
        for t in all_tasks
    }
    dependents: Set[str] = set()
    queue = [failed_id]
    while queue:
        current = queue.pop()
        for task_id, deps in depends_on_map.items():
            if current in deps and task_id not in dependents:
                dependents.add(task_id)
                queue.append(task_id)
    return dependents


_TASK_REF_FULL = re.compile(r"^\{\{task:([^.}\s]+)\.([^}\s]+)\}\}$")


def _resolve_task_refs(params: Dict, task_outputs: Dict[str, Dict]) -> Dict:
    """Replace {{task:TASK_ID.field}} placeholders with actual task output values.

    If an entire string value is a single reference, the original Python type
    (dict, list, int, etc.) is preserved.  If the reference appears as part of a
    larger string, the resolved value is coerced to a string.
    """

    def _resolve_value(v: Any) -> Any:
        if isinstance(v, str):
            full = _TASK_REF_FULL.match(v)
            if full:
                # Entire string is a reference — preserve the original type
                output = task_outputs.get(full.group(1), {})
                return output.get(full.group(2), "")

            # Partial reference(s) — inline-substitute as strings
            def _inline(m: re.Match) -> str:
                output = task_outputs.get(m.group(1), {})
                val = output.get(m.group(2), "")
                if isinstance(val, (dict, list)):
                    return json.dumps(val)
                return str(val)

            return _TASK_REF_PATTERN.sub(_inline, v)
        elif isinstance(v, dict):
            return {k: _resolve_value(vv) for k, vv in v.items()}
        elif isinstance(v, list):
            return [_resolve_value(item) for item in v]
        return v

    return {k: _resolve_value(v) for k, v in params.items()}


class PlanTools:
    """DAG-based plan creation and execution tools."""

    def __init__(self, db: Database, hitl_manager: Any, tool_dispatch: Callable):
        """Initialize plan tools.

        Args:
            db: Connected Database instance.
            hitl_manager: HITLManager for task-level HITL gates.
            tool_dispatch: Async callable ``(category, name, params) -> dict``
                           that executes a tool and returns its output as a dict.
        """
        self.db = db
        self.hitl_manager = hitl_manager
        self.tool_dispatch = tool_dispatch

    # ------------------------------------------------------------------
    # plan_create
    # ------------------------------------------------------------------

    async def create(self, req: PlanCreateRequest) -> PlanCreateResponse:
        """Validate and persist a new plan.

        Runs Kahn's algorithm to detect cycles and compute execution levels.

        Raises:
            PlanValidationError: On cycle, missing dependency, or duplicate IDs.
        """
        if not req.tasks:
            raise PlanValidationError("Plan must contain at least one task")

        # Duplicate task ID check
        task_ids = [t.id for t in req.tasks]
        seen: Set[str] = set()
        dupes: List[str] = []
        for tid in task_ids:
            if tid in seen:
                dupes.append(tid)
            seen.add(tid)
        if dupes:
            raise PlanValidationError(f"Duplicate task IDs: {list(set(dupes))}")

        # Validate on_failure values
        valid_policies = {"stop", "skip_dependents", "continue"}
        if req.on_failure not in valid_policies:
            raise PlanValidationError(
                f"Invalid on_failure '{req.on_failure}'. Must be one of: {valid_policies}"
            )
        for task in req.tasks:
            if task.on_failure is not None and task.on_failure not in valid_policies:
                raise PlanValidationError(
                    f"Task '{task.id}' has invalid on_failure '{task.on_failure}'"
                )

        # Compute execution levels (validates DAG structure)
        task_dicts = [{"id": t.id, "depends_on": t.depends_on} for t in req.tasks]
        execution_levels = _compute_execution_levels(task_dicts)

        level_map: Dict[str, int] = {}
        for level_idx, level_task_ids in enumerate(execution_levels):
            for tid in level_task_ids:
                level_map[tid] = level_idx

        conn = self.db.connection
        plan_id = _new_id()
        now = _now_iso()

        await conn.execute(
            """INSERT INTO plan_plans (id, name, status, on_failure, created_at, metadata)
               VALUES (?, ?, 'pending', ?, ?, ?)""",
            (plan_id, req.name, req.on_failure, now, json.dumps(req.metadata or {})),
        )

        for task in req.tasks:
            await conn.execute(
                """INSERT INTO plan_tasks
                   (id, plan_id, name, tool_category, tool_name, params,
                    depends_on, on_failure, require_hitl, status, execution_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    task.id,
                    plan_id,
                    task.name,
                    task.tool_category,
                    task.tool_name,
                    json.dumps(task.params or {}),
                    json.dumps(task.depends_on or []),
                    task.on_failure,
                    int(task.require_hitl),
                    level_map[task.id],
                ),
            )

        await conn.commit()
        logger.info("plan_create", plan_id=plan_id, tasks=len(req.tasks))

        return PlanCreateResponse(
            plan_id=plan_id,
            name=req.name,
            task_count=len(req.tasks),
            execution_levels=len(execution_levels),
            execution_order=execution_levels,
            created_at=now,
        )

    async def _resolve_plan_reference(
        self,
        conn,
        plan_ref: str,
        *,
        operation: str,
        wait_seconds: float = 0.0,
    ) -> Dict[str, Any]:
        """Resolve a plan reference by ID first, then by unique name."""
        retry_interval = 0.1
        attempts = max(1, int(wait_seconds / retry_interval) + 1)

        for attempt in range(attempts):
            cur = await conn.execute(
                "SELECT * FROM plan_plans WHERE id = ?", (plan_ref,)
            )
            plan = await cur.fetchone()
            if plan:
                return dict(plan)

            cur = await conn.execute(
                "SELECT * FROM plan_plans WHERE name = ? ORDER BY created_at DESC, id DESC",
                (plan_ref,),
            )
            matches = await cur.fetchall()

            if len(matches) == 1:
                resolved = dict(matches[0])
                logger.info(
                    "plan_reference_resolved",
                    operation=operation,
                    plan_reference=plan_ref,
                    resolved_plan_id=resolved["id"],
                    resolution="name",
                )
                return resolved

            if len(matches) > 1:
                sample_ids = [row["id"] for row in matches[:5]]
                extra_count = len(matches) - len(sample_ids)
                extra_text = f" (+{extra_count} more)" if extra_count > 0 else ""
                raise ValueError(
                    f"Multiple plans named '{plan_ref}' found (plan_ids: {', '.join(sample_ids)}{extra_text}). "
                    "Use the exact plan_id returned by plan_create."
                )

            if attempt < attempts - 1:
                await asyncio.sleep(retry_interval)

        raise PlanNotFoundError(
            f"Plan '{plan_ref}' not found. Pass the plan_id returned by plan_create."
        )

    # ------------------------------------------------------------------
    # plan_execute
    # ------------------------------------------------------------------

    async def execute(self, req: PlanExecuteRequest) -> PlanExecuteResponse:
        """Execute a plan synchronously, blocking until all tasks complete.

        Tasks within the same dependency level execute concurrently via
        asyncio.gather. Failure handling respects the plan's on_failure policy.

        Raises:
            PlanNotFoundError: If the plan does not exist.
            ValueError: If the plan is already running, completed, or cancelled.
        """
        conn = self.db.connection

        plan = await self._resolve_plan_reference(
            conn, req.plan_id, operation="execute", wait_seconds=1.0
        )
        plan_id = plan["id"]

        if plan["status"] == "running":
            raise ValueError(f"Plan '{plan_id}' is already running")
        if plan["status"] in ("completed", "failed"):
            raise ValueError(
                f"Plan '{plan_id}' already finished with status '{plan['status']}'. "
                "Create a new plan to re-run."
            )
        if plan["status"] == "cancelled":
            raise ValueError(f"Plan '{plan_id}' is cancelled and cannot be executed")

        # Load all tasks ordered by level
        cur = await conn.execute(
            "SELECT * FROM plan_tasks WHERE plan_id = ? ORDER BY execution_level, id",
            (plan_id,),
        )
        all_task_rows = await cur.fetchall()
        all_tasks = [dict(r) for r in all_task_rows]

        # Group by execution level
        levels: Dict[int, List[Dict]] = defaultdict(list)
        for task in all_tasks:
            levels[task["execution_level"]].append(task)

        now = _now_iso()
        await conn.execute(
            "UPDATE plan_plans SET status = 'running', started_at = ? WHERE id = ?",
            (now, plan_id),
        )
        await conn.commit()

        start_ms = int(time.time() * 1000)
        task_outputs: Dict[str, Dict] = {}
        failed_task_ids: Set[str] = set()  # all failed tasks (for counting)
        skip_ids: Set[str] = set()          # tasks whose dependents must be skipped
        stop_all = False                    # True when a stop-policy task has failed

        # Build a quick id→task map for policy lookups
        task_by_id: Dict[str, Dict] = {t["id"]: t for t in all_tasks}

        try:
            for level_idx in sorted(levels.keys()):
                # Check for external cancellation
                cur = await conn.execute(
                    "SELECT status FROM plan_plans WHERE id = ?", (plan_id,)
                )
                plan_row = await cur.fetchone()
                if plan_row and plan_row["status"] == "cancelled":
                    break

                level_tasks = levels[level_idx]
                tasks_to_run: List[Dict] = []
                tasks_to_skip: List[Dict] = []

                for task in level_tasks:
                    deps = _parse_json_field(task["depends_on"], [])
                    is_blocked = (
                        stop_all
                        or task["id"] in skip_ids
                        or any(d in skip_ids for d in deps)
                    )
                    if is_blocked:
                        tasks_to_skip.append(task)
                    else:
                        tasks_to_run.append(task)

                # Mark skipped tasks
                skip_now = _now_iso()
                for task in tasks_to_skip:
                    await conn.execute(
                        """UPDATE plan_tasks SET status = 'skipped', completed_at = ?
                           WHERE id = ? AND plan_id = ?""",
                        (skip_now, task["id"], plan_id),
                    )
                if tasks_to_skip:
                    await conn.commit()

                if not tasks_to_run:
                    continue

                # Execute all tasks at this level concurrently
                coroutines = [
                    self._execute_task(plan_id, task, task_outputs, plan)
                    for task in tasks_to_run
                ]
                results = await asyncio.gather(*coroutines, return_exceptions=True)

                for task, result in zip(tasks_to_run, results):
                    if isinstance(result, Exception):
                        task_id = task["id"]
                        failed_task_ids.add(task_id)
                        # Determine effective policy for THIS failing task
                        effective_policy = task["on_failure"] or plan["on_failure"]
                        if effective_policy == "stop":
                            stop_all = True
                            skip_ids.add(task_id)
                        elif effective_policy == "skip_dependents":
                            transitive = _get_transitive_dependents(task_id, all_tasks)
                            skip_ids.update(transitive)
                        # "continue": don't block anything
                    else:
                        task_id, output = result
                        task_outputs[task_id] = output

        except asyncio.CancelledError:
            await conn.execute(
                "UPDATE plan_plans SET status = 'cancelled', completed_at = ? WHERE id = ?",
                (_now_iso(), plan_id),
            )
            await conn.commit()
            raise

        # Tally final counts from DB
        cur = await conn.execute(
            "SELECT status, COUNT(*) as cnt FROM plan_tasks WHERE plan_id = ? GROUP BY status",
            (plan_id,),
        )
        status_counts: Dict[str, int] = {r["status"]: r["cnt"] for r in await cur.fetchall()}

        tasks_completed = status_counts.get("completed", 0)
        tasks_failed = status_counts.get("failed", 0)
        tasks_skipped = status_counts.get("skipped", 0)

        # Check if plan was cancelled externally during execution
        cur = await conn.execute(
            "SELECT status FROM plan_plans WHERE id = ?", (plan_id,)
        )
        current_plan_status = (await cur.fetchone())["status"]

        if current_plan_status != "cancelled":
            final_status = "completed" if tasks_failed == 0 else "failed"
            await conn.execute(
                "UPDATE plan_plans SET status = ?, completed_at = ? WHERE id = ?",
                (final_status, _now_iso(), plan_id),
            )
            await conn.commit()
        else:
            final_status = "cancelled"

        duration_ms = int(time.time() * 1000) - start_ms
        logger.info(
            "plan_execute",
            plan_id=plan_id,
            status=final_status,
            completed=tasks_completed,
            failed=tasks_failed,
            skipped=tasks_skipped,
            duration_ms=duration_ms,
        )

        return PlanExecuteResponse(
            plan_id=plan_id,
            status=final_status,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            tasks_skipped=tasks_skipped,
            duration_ms=duration_ms,
        )

    async def _execute_task(
        self,
        plan_id: str,
        task: Dict,
        task_outputs: Dict[str, Dict],
        plan: Dict,
    ) -> tuple:
        """Execute a single plan task. Returns ``(task_id, output_dict)`` on success."""
        conn = self.db.connection
        task_id = task["id"]

        # Resolve {{task:ID.field}} references
        raw_params = _parse_json_field(task["params"], {})
        try:
            resolved_params = _resolve_task_refs(raw_params, task_outputs)
        except Exception as e:
            error_msg = f"Failed to resolve task references: {e}"
            await self._update_task(conn, plan_id, task_id, "failed", error=error_msg)
            raise ValueError(error_msg) from e

        # HITL gate for tasks that require approval
        if task.get("require_hitl"):
            try:
                hitl_req = await self.hitl_manager.create_request(
                    tool_name=task["tool_name"],
                    tool_category=task["tool_category"],
                    request_params=resolved_params,
                    request_context={"plan_id": plan_id, "task_id": task_id},
                    policy_rule_matched="plan_task_require_hitl",
                )
                decision = await self.hitl_manager.wait_for_decision(hitl_req.id)
                if decision == "rejected":
                    error_msg = "Task rejected via HITL"
                    await self._update_task(conn, plan_id, task_id, "failed", error=error_msg)
                    raise ValueError(error_msg)
                elif decision == "expired":
                    error_msg = "HITL approval timed out"
                    await self._update_task(conn, plan_id, task_id, "failed", error=error_msg)
                    raise ValueError(error_msg)
            except (ValueError, TimeoutError):
                raise
            except Exception as e:
                error_msg = f"HITL error: {e}"
                await self._update_task(conn, plan_id, task_id, "failed", error=error_msg)
                raise ValueError(error_msg) from e

        # Mark as running
        await self._update_task(conn, plan_id, task_id, "running")

        try:
            output = await self.tool_dispatch(
                task["tool_category"], task["tool_name"], resolved_params
            )
            output_dict: Dict = output if isinstance(output, dict) else {"result": str(output)}
            await self._update_task(conn, plan_id, task_id, "completed", output=output_dict)
            return task_id, output_dict

        except Exception as e:
            await self._update_task(conn, plan_id, task_id, "failed", error=str(e))
            raise

    async def _update_task(
        self,
        conn,
        plan_id: str,
        task_id: str,
        status: str,
        output: Optional[Dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Persist a task status change to the database."""
        now = _now_iso()
        if status == "running":
            await conn.execute(
                """UPDATE plan_tasks SET status = 'running', started_at = ?
                   WHERE id = ? AND plan_id = ?""",
                (now, task_id, plan_id),
            )
        else:
            await conn.execute(
                """UPDATE plan_tasks
                   SET status = ?, output = ?, error = ?, completed_at = ?
                   WHERE id = ? AND plan_id = ?""",
                (
                    status,
                    json.dumps(output) if output is not None else None,
                    error,
                    now,
                    task_id,
                    plan_id,
                ),
            )
        await conn.commit()

    # ------------------------------------------------------------------
    # plan_status
    # ------------------------------------------------------------------

    async def status(self, req: PlanStatusRequest) -> PlanStatusResponse:
        """Get current plan and per-task status.

        Raises:
            PlanNotFoundError: If the plan does not exist.
        """
        conn = self.db.connection

        plan = await self._resolve_plan_reference(
            conn, req.plan_id, operation="status"
        )
        plan_id = plan["id"]

        cur = await conn.execute(
            "SELECT * FROM plan_tasks WHERE plan_id = ? ORDER BY execution_level, id",
            (plan_id,),
        )
        task_rows = await cur.fetchall()

        tasks = [
            PlanTaskStatus(
                id=row["id"],
                name=row["name"],
                tool_category=row["tool_category"],
                tool_name=row["tool_name"],
                status=row["status"],
                output=_parse_json_field(row["output"], None),
                error=row["error"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                depends_on=_parse_json_field(row["depends_on"], []),
                execution_level=row["execution_level"],
            )
            for row in task_rows
        ]

        statuses = [t.status for t in tasks]
        return PlanStatusResponse(
            plan_id=plan_id,
            name=plan["name"],
            status=plan["status"],
            on_failure=plan["on_failure"],
            created_at=plan["created_at"],
            started_at=plan["started_at"],
            completed_at=plan["completed_at"],
            tasks=tasks,
            tasks_total=len(tasks),
            tasks_completed=statuses.count("completed"),
            tasks_failed=statuses.count("failed"),
            tasks_skipped=statuses.count("skipped"),
            tasks_running=statuses.count("running"),
        )

    # ------------------------------------------------------------------
    # plan_list
    # ------------------------------------------------------------------

    async def list(self) -> PlanListResponse:
        """List all plans with summary information."""
        conn = self.db.connection

        cur = await conn.execute(
            "SELECT * FROM plan_plans ORDER BY created_at DESC"
        )
        plan_rows = await cur.fetchall()

        plans: List[PlanListItem] = []
        for row in plan_rows:
            tcur = await conn.execute(
                "SELECT COUNT(*) as cnt FROM plan_tasks WHERE plan_id = ?",
                (row["id"],),
            )
            task_count = (await tcur.fetchone())["cnt"]
            plans.append(
                PlanListItem(
                    plan_id=row["id"],
                    name=row["name"],
                    status=row["status"],
                    on_failure=row["on_failure"],
                    task_count=task_count,
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                )
            )

        return PlanListResponse(plans=plans, total=len(plans))

    # ------------------------------------------------------------------
    # plan_cancel
    # ------------------------------------------------------------------

    async def cancel(self, req: PlanCancelRequest) -> PlanCancelResponse:
        """Cancel a plan, marking all pending/running tasks as skipped.

        Raises:
            PlanNotFoundError: If the plan does not exist.
            ValueError: If the plan is already completed or cancelled.
        """
        conn = self.db.connection

        plan = await self._resolve_plan_reference(
            conn, req.plan_id, operation="cancel"
        )
        plan_id = plan["id"]

        if plan["status"] in ("completed", "cancelled"):
            raise ValueError(
                f"Plan '{plan_id}' is already '{plan['status']}' and cannot be cancelled"
            )

        now = _now_iso()

        # Count tasks that will be cancelled
        cur = await conn.execute(
            """SELECT COUNT(*) as cnt FROM plan_tasks
               WHERE plan_id = ? AND status IN ('pending', 'ready', 'running')""",
            (plan_id,),
        )
        cancelled_count = (await cur.fetchone())["cnt"]

        await conn.execute(
            """UPDATE plan_tasks SET status = 'skipped', completed_at = ?
               WHERE plan_id = ? AND status IN ('pending', 'ready', 'running')""",
            (now, plan_id),
        )
        await conn.execute(
            "UPDATE plan_plans SET status = 'cancelled', completed_at = ? WHERE id = ?",
            (now, plan_id),
        )
        await conn.commit()

        logger.info("plan_cancel", plan_id=plan_id, cancelled_tasks=cancelled_count)

        return PlanCancelResponse(
            plan_id=plan_id,
            cancelled_tasks=cancelled_count,
            status="cancelled",
        )
