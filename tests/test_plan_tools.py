"""Tests for PlanTools — LLM-driven plan tracking workflow."""

import os
import tempfile
from unittest.mock import MagicMock

import pytest
import pytest_asyncio


_TEST_DB_DIR = tempfile.mkdtemp()
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test_plan.db")
_TEST_WORKSPACE = tempfile.mkdtemp()

os.environ.setdefault("DB_PATH", _TEST_DB_PATH)
os.environ["DB_PATH"] = _TEST_DB_PATH
os.environ["WORKSPACE_BASE_DIR"] = _TEST_WORKSPACE


@pytest_asyncio.fixture(scope="module")
async def plan_db():
    """Connected Database instance for plan tests."""
    from anyide.core.database import Database

    db = Database(_TEST_DB_PATH)
    await db.connect()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def plan_tools(plan_db):
    """Fresh PlanTools with clean plan tables."""
    from anyide.modules.plan.tools import PlanTools

    conn = plan_db.connection
    await conn.execute("DELETE FROM plan_tasks")
    await conn.execute("DELETE FROM plan_plans")
    await conn.commit()

    async def _dispatch(_category, _name, _params):
        return {"ok": True}

    return PlanTools(plan_db, MagicMock(), _dispatch)


def make_task(
    tid,
    name=None,
    tool_cat="fs",
    tool_name="read",
    params=None,
    depends_on=None,
    on_failure=None,
    require_hitl=False,
):
    from anyide.models import PlanTaskDef

    return PlanTaskDef(
        id=tid,
        name=name or f"Task {tid}",
        tool_category=tool_cat,
        tool_name=tool_name,
        params=params or {},
        depends_on=depends_on or [],
        on_failure=on_failure,
        require_hitl=require_hitl,
    )


def make_create_req(name, tasks, on_failure="stop"):
    from anyide.models import PlanCreateRequest

    return PlanCreateRequest(name=name, tasks=tasks, on_failure=on_failure)


class TestPlanCreate:
    @pytest.mark.asyncio
    async def test_create_single_task(self, plan_tools):
        req = make_create_req("single", [make_task("t1")])
        result = await plan_tools.create(req)

        assert result.plan_id
        assert result.task_count == 1
        assert result.execution_order == [["t1"]]

    @pytest.mark.asyncio
    async def test_create_cycle_raises(self, plan_tools):
        from anyide.modules.plan.tools import PlanValidationError

        tasks = [
            make_task("a", depends_on=["b"]),
            make_task("b", depends_on=["a"]),
        ]
        with pytest.raises(PlanValidationError, match="Cycle"):
            await plan_tools.create(make_create_req("cycle", tasks))

    @pytest.mark.asyncio
    async def test_create_duplicate_task_ids_raises(self, plan_tools):
        from anyide.modules.plan.tools import PlanValidationError

        with pytest.raises(PlanValidationError, match="Duplicate"):
            await plan_tools.create(make_create_req("dup", [make_task("x"), make_task("x")]))


class TestPlanExecuteReadiness:
    @pytest.mark.asyncio
    async def test_execute_starts_plan_and_returns_ready_tasks(self, plan_tools):
        from anyide.models import PlanExecuteRequest

        created = await plan_tools.create(
            make_create_req(
                "chain",
                [
                    make_task("t1", tool_name="first"),
                    make_task("t2", tool_name="second", depends_on=["t1"]),
                ],
            )
        )

        result = await plan_tools.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.plan_id == created.plan_id
        assert result.status == "running"
        assert [t.id for t in result.ready_tasks] == ["t1"]
        assert result.tasks_total == 2
        assert result.tasks_pending == 2

    @pytest.mark.asyncio
    async def test_execute_resolves_task_references_from_completed_outputs(self, plan_tools):
        from anyide.models import PlanExecuteRequest, PlanTaskUpdateRequest

        created = await plan_tools.create(
            make_create_req(
                "refs",
                [
                    make_task("producer", params={}),
                    make_task(
                        "consumer",
                        params={"input": "{{task:producer.value}}"},
                        depends_on=["producer"],
                    ),
                ],
            )
        )

        await plan_tools.update_task(
            PlanTaskUpdateRequest(
                plan_id=created.plan_id,
                task_id="producer",
                status="completed",
                output={"value": "hello"},
            )
        )

        result = await plan_tools.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert [t.id for t in result.ready_tasks] == ["consumer"]
        assert result.ready_tasks[0].resolved_params["input"] == "hello"

    @pytest.mark.asyncio
    async def test_execute_by_unique_plan_name(self, plan_tools):
        from anyide.models import PlanExecuteRequest

        created = await plan_tools.create(make_create_req("by_name", [make_task("x1")]))
        result = await plan_tools.execute(PlanExecuteRequest(plan_id="by_name"))

        assert result.plan_id == created.plan_id

    @pytest.mark.asyncio
    async def test_execute_terminal_plan_returns_empty_ready(self, plan_tools):
        from anyide.models import PlanExecuteRequest, PlanTaskUpdateRequest

        created = await plan_tools.create(make_create_req("terminal", [make_task("done")]))
        await plan_tools.update_task(
            PlanTaskUpdateRequest(
                plan_id=created.plan_id,
                task_id="done",
                status="completed",
                output={"ok": True},
            )
        )

        result = await plan_tools.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.status == "completed"
        assert result.ready_tasks == []
        assert result.tasks_completed == 1


class TestPlanTaskUpdate:
    @pytest.mark.asyncio
    async def test_update_running_requires_task_to_be_ready(self, plan_tools):
        from anyide.models import PlanTaskUpdateRequest

        created = await plan_tools.create(
            make_create_req("ready_check", [make_task("a"), make_task("b", depends_on=["a"])])
        )

        with pytest.raises(ValueError, match="not ready"):
            await plan_tools.update_task(
                PlanTaskUpdateRequest(plan_id=created.plan_id, task_id="b", status="running")
            )

    @pytest.mark.asyncio
    async def test_update_completed_advances_plan(self, plan_tools):
        from anyide.models import PlanStatusRequest, PlanTaskUpdateRequest

        created = await plan_tools.create(make_create_req("advance", [make_task("a")]))

        update = await plan_tools.update_task(
            PlanTaskUpdateRequest(
                plan_id=created.plan_id,
                task_id="a",
                status="completed",
                output={"result": 1},
            )
        )

        assert update.plan_status == "completed"
        assert update.tasks_completed == 1

        status = await plan_tools.status(PlanStatusRequest(plan_id=created.plan_id))
        assert status.status == "completed"
        assert status.tasks[0].output == {"result": 1}

    @pytest.mark.asyncio
    async def test_failed_task_stop_policy_skips_remaining(self, plan_tools):
        from anyide.models import PlanStatusRequest, PlanTaskUpdateRequest

        created = await plan_tools.create(
            make_create_req("stop_policy", [make_task("a"), make_task("b")], on_failure="stop")
        )

        update = await plan_tools.update_task(
            PlanTaskUpdateRequest(
                plan_id=created.plan_id,
                task_id="a",
                status="failed",
                error="boom",
            )
        )

        assert update.plan_status == "failed"
        assert update.tasks_failed == 1
        assert update.tasks_skipped == 1

        status = await plan_tools.status(PlanStatusRequest(plan_id=created.plan_id))
        task_map = {t.id: t.status for t in status.tasks}
        assert task_map["a"] == "failed"
        assert task_map["b"] == "skipped"

    @pytest.mark.asyncio
    async def test_failed_task_skip_dependents_policy(self, plan_tools):
        from anyide.models import PlanExecuteRequest, PlanTaskUpdateRequest

        created = await plan_tools.create(
            make_create_req(
                "skip_dependents",
                [
                    make_task("a"),
                    make_task("b", depends_on=["a"]),
                    make_task("c", depends_on=["b"]),
                    make_task("d"),
                ],
                on_failure="skip_dependents",
            )
        )

        update = await plan_tools.update_task(
            PlanTaskUpdateRequest(plan_id=created.plan_id, task_id="a", status="failed", error="x")
        )

        assert update.tasks_failed == 1
        assert update.tasks_skipped == 2  # b + c

        execute = await plan_tools.execute(PlanExecuteRequest(plan_id=created.plan_id))
        assert [t.id for t in execute.ready_tasks] == ["d"]

    @pytest.mark.asyncio
    async def test_failed_task_continue_policy_allows_dependents(self, plan_tools):
        from anyide.models import PlanExecuteRequest, PlanTaskUpdateRequest

        created = await plan_tools.create(
            make_create_req(
                "continue_policy",
                [make_task("a"), make_task("b", depends_on=["a"])],
                on_failure="continue",
            )
        )

        await plan_tools.update_task(
            PlanTaskUpdateRequest(plan_id=created.plan_id, task_id="a", status="failed", error="x")
        )

        execute = await plan_tools.execute(PlanExecuteRequest(plan_id=created.plan_id))
        assert [t.id for t in execute.ready_tasks] == ["b"]

    @pytest.mark.asyncio
    async def test_update_terminal_task_rejected(self, plan_tools):
        from anyide.models import PlanTaskUpdateRequest

        created = await plan_tools.create(make_create_req("terminal_update", [make_task("a")]))
        await plan_tools.update_task(
            PlanTaskUpdateRequest(plan_id=created.plan_id, task_id="a", status="completed", output={"ok": True})
        )

        with pytest.raises(ValueError, match="already in terminal status"):
            await plan_tools.update_task(
                PlanTaskUpdateRequest(plan_id=created.plan_id, task_id="a", status="failed", error="nope")
            )


class TestPlanStatusListCancel:
    @pytest.mark.asyncio
    async def test_status_pending_plan(self, plan_tools):
        from anyide.models import PlanStatusRequest

        created = await plan_tools.create(make_create_req("pending", [make_task("x1"), make_task("x2")]))
        status = await plan_tools.status(PlanStatusRequest(plan_id=created.plan_id))

        assert status.status == "pending"
        assert status.tasks_total == 2

    @pytest.mark.asyncio
    async def test_list_returns_task_counts(self, plan_tools):
        await plan_tools.create(make_create_req("alpha", [make_task("a1")]))
        await plan_tools.create(make_create_req("beta", [make_task("b1"), make_task("b2")]))

        result = await plan_tools.list()
        names = {p.name for p in result.plans}
        assert {"alpha", "beta"}.issubset(names)

    @pytest.mark.asyncio
    async def test_cancel_pending_plan(self, plan_tools):
        from anyide.models import PlanCancelRequest, PlanStatusRequest

        created = await plan_tools.create(make_create_req("to_cancel", [make_task("c1"), make_task("c2")]))
        cancel_result = await plan_tools.cancel(PlanCancelRequest(plan_id=created.plan_id))

        assert cancel_result.status == "cancelled"
        assert cancel_result.cancelled_tasks == 2

        status = await plan_tools.status(PlanStatusRequest(plan_id=created.plan_id))
        assert status.status == "cancelled"


class TestHelperFunctions:
    def test_compute_execution_levels_linear(self):
        from anyide.modules.plan.tools import _compute_execution_levels

        tasks = [
            {"id": "a", "depends_on": []},
            {"id": "b", "depends_on": ["a"]},
            {"id": "c", "depends_on": ["b"]},
        ]
        levels = _compute_execution_levels(tasks)
        assert levels == [["a"], ["b"], ["c"]]

    def test_compute_execution_levels_detects_cycle(self):
        from anyide.modules.plan.tools import PlanValidationError, _compute_execution_levels

        tasks = [{"id": "a", "depends_on": ["b"]}, {"id": "b", "depends_on": ["a"]}]
        with pytest.raises(PlanValidationError, match="Cycle"):
            _compute_execution_levels(tasks)

    def test_resolve_task_refs_nested(self):
        from anyide.modules.plan.tools import _resolve_task_refs

        params = {"a": "{{task:t1.x}}", "b": {"v": "{{task:t2.y}}"}}
        outputs = {"t1": {"x": "foo"}, "t2": {"y": "bar"}}
        resolved = _resolve_task_refs(params, outputs)
        assert resolved["a"] == "foo"
        assert resolved["b"]["v"] == "bar"


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

def _api_client():
    from fastapi.testclient import TestClient
    from anyide.main import app

    return TestClient(app, raise_server_exceptions=False)


def _api_create_plan(client, name, tasks, on_failure="stop"):
    return client.post(
        "/api/tools/plan/create",
        json={"name": name, "tasks": tasks, "on_failure": on_failure},
    )


class TestPlanIntegration:
    def test_execute_returns_ready_tasks_via_api(self):
        tasks = [
            {"id": "t1", "name": "Task 1", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": []},
            {"id": "t2", "name": "Task 2", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": ["t1"]},
        ]
        with _api_client() as client:
            create = _api_create_plan(client, "api_execute", tasks)
            assert create.status_code == 200
            plan_id = create.json()["plan_id"]

            execute = client.post("/api/tools/plan/execute", json={"plan_id": plan_id})

        assert execute.status_code == 200
        data = execute.json()
        assert data["status"] == "running"
        assert [t["id"] for t in data["ready_tasks"]] == ["t1"]

    def test_update_task_and_finalize_via_api(self):
        tasks = [{"id": "t3", "name": "Task 1", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": []}]
        with _api_client() as client:
            create = _api_create_plan(client, "api_update", tasks)
            assert create.status_code == 200
            plan_id = create.json()["plan_id"]

            update = client.post(
                "/api/tools/plan/update_task",
                json={
                    "plan_id": plan_id,
                    "task_id": "t3",
                    "status": "completed",
                    "output": {"content": "ok"},
                },
            )
            status = client.post("/api/tools/plan/status", json={"plan_id": plan_id})

        assert update.status_code == 200
        assert update.json()["plan_status"] == "completed"
        assert status.status_code == 200
        assert status.json()["status"] == "completed"

    def test_update_task_not_found_returns_404(self):
        with _api_client() as client:
            response = client.post(
                "/api/tools/plan/update_task",
                json={"plan_id": "missing", "task_id": "x", "status": "completed", "output": {}},
            )
        assert response.status_code == 404
