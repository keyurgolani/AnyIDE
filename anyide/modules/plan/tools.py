"""Plan tools — DAG-based multi-step planning and status tracking."""

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from anyide.core.database import Database
from anyide.logging_config import get_logger
from anyide.models import (
    PlanCreateRequest,
    PlanCreateResponse,
    PlanExecuteRequest,
    PlanExecuteResponse,
    PlanReadyTask,
    PlanStatusRequest,
    PlanStatusResponse,
    PlanTaskUpdateRequest,
    PlanTaskUpdateResponse,
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
    """DAG-based plan creation and external-orchestrator status tools."""

    def __init__(self, db: Database, hitl_manager: Any, tool_dispatch: Callable):
        """Initialize plan tools.

        Args:
            db: Connected Database instance.
            hitl_manager: Reserved for compatibility with module context wiring.
            tool_dispatch: Reserved for compatibility with module context wiring.
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
        """Evaluate plan state and return tasks that are currently ready to run."""
        conn = self.db.connection

        plan = await self._resolve_plan_reference(
            conn, req.plan_id, operation="execute", wait_seconds=1.0
        )
        plan_id = plan["id"]

        if plan["status"] == "pending":
            now = _now_iso()
            await conn.execute(
                """UPDATE plan_plans
                   SET status = 'running', started_at = COALESCE(started_at, ?)
                   WHERE id = ?""",
                (now, plan_id),
            )
            await conn.commit()
            plan["status"] = "running"
            plan["started_at"] = plan.get("started_at") or now

        plan, task_rows = await self._sync_plan_status(conn, plan_id)
        ready_tasks = self._build_ready_tasks(plan, task_rows)
        counts = self._compute_status_counts(task_rows)

        logger.info(
            "plan_execute_ready_snapshot",
            plan_id=plan_id,
            status=plan["status"],
            ready_tasks=len(ready_tasks),
            pending=counts["pending"],
            running=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
            skipped=counts["skipped"],
        )

        return PlanExecuteResponse(
            plan_id=plan_id,
            status=plan["status"],
            ready_tasks=ready_tasks,
            tasks_total=len(task_rows),
            tasks_pending=counts["pending"],
            tasks_running=counts["running"],
            tasks_completed=counts["completed"],
            tasks_failed=counts["failed"],
            tasks_skipped=counts["skipped"],
            started_at=plan.get("started_at"),
            completed_at=plan.get("completed_at"),
        )

    # ------------------------------------------------------------------
    # plan_update_task
    # ------------------------------------------------------------------

    async def update_task(self, req: PlanTaskUpdateRequest) -> PlanTaskUpdateResponse:
        """Update a single task status after external task execution."""
        conn = self.db.connection
        plan = await self._resolve_plan_reference(
            conn, req.plan_id, operation="update_task"
        )
        plan_id = plan["id"]

        if plan["status"] == "cancelled":
            raise ValueError(f"Plan '{plan_id}' is cancelled and cannot be updated")

        valid_statuses = {"running", "completed", "failed", "skipped"}
        if req.status not in valid_statuses:
            raise ValueError(
                f"Invalid task status '{req.status}'. Must be one of: {sorted(valid_statuses)}"
            )

        cur = await conn.execute(
            "SELECT * FROM plan_tasks WHERE plan_id = ? AND id = ?",
            (plan_id, req.task_id),
        )
        task_row = await cur.fetchone()
        if task_row is None:
            raise PlanNotFoundError(
                f"Task '{req.task_id}' not found in plan '{plan_id}'."
            )

        task = dict(task_row)
        if task["status"] in ("completed", "failed", "skipped"):
            raise ValueError(
                f"Task '{req.task_id}' is already in terminal status '{task['status']}'"
            )

        all_task_rows = await self._get_plan_tasks(conn, plan_id)
        task_map = {t["id"]: t for t in all_task_rows}
        ready_before_update = self._is_task_ready(task, task_map, plan)

        if req.status == "running" and not ready_before_update:
            raise ValueError(f"Task '{req.task_id}' is not ready; dependencies are incomplete")

        if req.status in ("completed", "failed") and task["status"] == "pending" and not ready_before_update:
            raise ValueError(f"Task '{req.task_id}' is not ready; dependencies are incomplete")

        now = _now_iso()
        if req.status == "running":
            await conn.execute(
                """UPDATE plan_tasks
                   SET status = 'running', started_at = COALESCE(started_at, ?)
                   WHERE plan_id = ? AND id = ?""",
                (now, plan_id, req.task_id),
            )
        else:
            await conn.execute(
                """UPDATE plan_tasks
                   SET status = ?, output = ?, error = ?,
                       started_at = COALESCE(started_at, ?), completed_at = ?
                   WHERE plan_id = ? AND id = ?""",
                (
                    req.status,
                    json.dumps(req.output) if req.output is not None else None,
                    req.error,
                    now,
                    now,
                    plan_id,
                    req.task_id,
                ),
            )

        if plan["status"] == "pending":
            await conn.execute(
                """UPDATE plan_plans
                   SET status = 'running', started_at = COALESCE(started_at, ?)
                   WHERE id = ?""",
                (now, plan_id),
            )

        if req.status == "failed":
            await self._apply_failure_policy(conn, plan, req.task_id)

        await conn.commit()

        plan, task_rows = await self._sync_plan_status(conn, plan_id)
        counts = self._compute_status_counts(task_rows)
        ready_tasks = self._build_ready_tasks(plan, task_rows)

        logger.info(
            "plan_update_task",
            plan_id=plan_id,
            task_id=req.task_id,
            task_status=req.status,
            plan_status=plan["status"],
            pending=counts["pending"],
            running=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
            skipped=counts["skipped"],
        )

        return PlanTaskUpdateResponse(
            plan_id=plan_id,
            task_id=req.task_id,
            task_status=req.status,
            plan_status=plan["status"],
            tasks_total=len(task_rows),
            tasks_pending=counts["pending"],
            tasks_running=counts["running"],
            tasks_completed=counts["completed"],
            tasks_failed=counts["failed"],
            tasks_skipped=counts["skipped"],
            ready_tasks=ready_tasks,
        )

    async def _apply_failure_policy(self, conn, plan: Dict[str, Any], failed_task_id: str) -> None:
        """Apply effective on-failure policy after a task is marked failed."""
        plan_id = plan["id"]
        all_tasks = await self._get_plan_tasks(conn, plan_id)
        task_map = {t["id"]: t for t in all_tasks}
        failed_task = task_map.get(failed_task_id)
        if failed_task is None:
            return

        policy = self._effective_failure_policy(failed_task, plan)
        if policy == "continue":
            return

        skip_now = _now_iso()
        if policy == "stop":
            await conn.execute(
                """UPDATE plan_tasks
                   SET status = 'skipped',
                       started_at = COALESCE(started_at, ?),
                       completed_at = ?
                   WHERE plan_id = ? AND id != ?
                     AND status IN ('pending', 'running')""",
                (skip_now, skip_now, plan_id, failed_task_id),
            )
            return

        # skip_dependents
        dependents = sorted(_get_transitive_dependents(failed_task_id, all_tasks))
        if not dependents:
            return
        placeholders = ", ".join("?" for _ in dependents)
        await conn.execute(
            f"""UPDATE plan_tasks
                SET status = 'skipped',
                    started_at = COALESCE(started_at, ?),
                    completed_at = ?
                WHERE plan_id = ?
                  AND id IN ({placeholders})
                  AND status IN ('pending', 'running')""",
            (skip_now, skip_now, plan_id, *dependents),
        )

    async def _get_plan_tasks(self, conn, plan_id: str) -> List[Dict[str, Any]]:
        """Load all tasks for a plan ordered deterministically for readiness checks."""
        cur = await conn.execute(
            "SELECT * FROM plan_tasks WHERE plan_id = ? ORDER BY execution_level, id",
            (plan_id,),
        )
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

    def _compute_status_counts(self, task_rows: List[Dict[str, Any]]) -> Dict[str, int]:
        """Return per-status counts for plan tasks."""
        counts = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
        }
        for row in task_rows:
            status = row["status"]
            if status in counts:
                counts[status] += 1
        return counts

    def _effective_failure_policy(self, task: Dict[str, Any], plan: Dict[str, Any]) -> str:
        """Resolve task-level failure policy with plan-level fallback."""
        return task.get("on_failure") or plan["on_failure"]

    def _dependency_satisfied(self, dep_task: Dict[str, Any], plan: Dict[str, Any]) -> bool:
        """Whether a dependency task is satisfied for downstream readiness."""
        dep_status = dep_task["status"]
        if dep_status == "completed":
            return True
        if dep_status == "failed":
            return self._effective_failure_policy(dep_task, plan) == "continue"
        return False

    def _is_task_ready(
        self,
        task: Dict[str, Any],
        task_map: Dict[str, Dict[str, Any]],
        plan: Dict[str, Any],
    ) -> bool:
        """Check whether a pending task has all dependencies satisfied."""
        if task["status"] != "pending":
            return False
        for dep_id in _parse_json_field(task["depends_on"], []):
            dep_task = task_map.get(dep_id)
            if dep_task is None or not self._dependency_satisfied(dep_task, plan):
                return False
        return True

    def _build_ready_tasks(
        self,
        plan: Dict[str, Any],
        task_rows: List[Dict[str, Any]],
    ) -> List[PlanReadyTask]:
        """Build the current ready task list with params resolved from completed outputs."""
        task_map = {t["id"]: t for t in task_rows}
        outputs = {
            t["id"]: _parse_json_field(t.get("output"), {}) or {}
            for t in task_rows
            if t["status"] == "completed"
        }

        ready_tasks: List[PlanReadyTask] = []
        for task in task_rows:
            if not self._is_task_ready(task, task_map, plan):
                continue
            raw_params = _parse_json_field(task.get("params"), {}) or {}
            resolved_params = _resolve_task_refs(raw_params, outputs)
            ready_tasks.append(
                PlanReadyTask(
                    id=task["id"],
                    name=task["name"],
                    tool_category=task["tool_category"],
                    tool_name=task["tool_name"],
                    resolved_params=resolved_params,
                    depends_on=_parse_json_field(task["depends_on"], []),
                    execution_level=task["execution_level"],
                    require_hitl=bool(task.get("require_hitl")),
                )
            )
        return ready_tasks

    def _derive_plan_status(self, plan: Dict[str, Any], counts: Dict[str, int]) -> str:
        """Derive canonical plan status from plan row + task counts."""
        if plan["status"] == "cancelled":
            return "cancelled"

        if counts["running"] > 0:
            return "running"

        if counts["pending"] == 0:
            return "failed" if counts["failed"] > 0 else "completed"

        return "pending" if plan["status"] == "pending" else "running"

    async def _sync_plan_status(self, conn, plan_id: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Recompute and persist plan status from current task states."""
        cur = await conn.execute("SELECT * FROM plan_plans WHERE id = ?", (plan_id,))
        row = await cur.fetchone()
        if row is None:
            raise PlanNotFoundError(
                f"Plan '{plan_id}' not found. Pass the plan_id returned by plan_create."
            )
        plan = dict(row)
        task_rows = await self._get_plan_tasks(conn, plan_id)
        counts = self._compute_status_counts(task_rows)
        derived_status = self._derive_plan_status(plan, counts)

        if plan["status"] == "cancelled":
            return plan, task_rows

        now = _now_iso()
        started_at = plan["started_at"]
        if derived_status != "pending" and not started_at:
            started_at = now

        if derived_status in ("completed", "failed"):
            completed_at = plan["completed_at"] or now
        else:
            completed_at = None

        needs_update = (
            derived_status != plan["status"]
            or started_at != plan["started_at"]
            or completed_at != plan["completed_at"]
        )
        if needs_update:
            await conn.execute(
                """UPDATE plan_plans
                   SET status = ?, started_at = ?, completed_at = ?
                   WHERE id = ?""",
                (derived_status, started_at, completed_at, plan_id),
            )
            await conn.commit()
            plan["status"] = derived_status
            plan["started_at"] = started_at
            plan["completed_at"] = completed_at

        return plan, task_rows

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
