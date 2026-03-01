"""Tests for PlanTools — DAG-based plan creation and execution."""

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Set DB path BEFORE any app imports so the module-level Database() uses it
# ---------------------------------------------------------------------------
_TEST_DB_DIR = tempfile.mkdtemp()
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test_plan.db")
_TEST_WORKSPACE = tempfile.mkdtemp()

os.environ.setdefault("DB_PATH", _TEST_DB_PATH)
os.environ["DB_PATH"] = _TEST_DB_PATH
os.environ["WORKSPACE_BASE_DIR"] = _TEST_WORKSPACE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def plan_db():
    """A connected Database instance used for all plan tool tests."""
    from anyide.core.database import Database

    db = Database(_TEST_DB_PATH)
    await db.connect()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def plan_tools(plan_db):
    """Fresh PlanTools instance — DB is shared but plan/task tables are wiped."""
    from anyide.modules.plan.tools import PlanTools

    conn = plan_db.connection
    await conn.execute("DELETE FROM plan_tasks")
    await conn.execute("DELETE FROM plan_plans")
    await conn.commit()

    # Default no-op dispatch: returns {"ok": True}
    async def _dispatch(category, name, params):
        return {"ok": True, "category": category, "name": name}

    mock_hitl = MagicMock()
    return PlanTools(plan_db, mock_hitl, _dispatch)


def _make_plan_tools(plan_db, dispatch=None, hitl=None):
    """Helper to build a PlanTools with custom dispatch/hitl."""
    from anyide.modules.plan.tools import PlanTools

    if dispatch is None:
        async def dispatch(category, name, params):
            return {"ok": True}

    if hitl is None:
        hitl = MagicMock()

    return PlanTools(plan_db, hitl, dispatch)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def make_task(tid, name=None, tool_cat="fs", tool_name="read", params=None, depends_on=None, on_failure=None, require_hitl=False):
    """Build a PlanTaskDef dict quickly."""
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


# ---------------------------------------------------------------------------
# TestPlanCreate
# ---------------------------------------------------------------------------


class TestPlanCreate:
    """Tests for plan_create."""

    @pytest.mark.asyncio
    async def test_create_single_task(self, plan_tools):
        req = make_create_req("single", [make_task("t1")])
        result = await plan_tools.create(req)

        assert result.plan_id
        assert result.name == "single"
        assert result.task_count == 1
        assert result.execution_levels == 1
        assert result.execution_order == [["t1"]]

    @pytest.mark.asyncio
    async def test_create_sequential_chain(self, plan_tools):
        """A → B → C should produce three execution levels."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
            make_task("c", depends_on=["b"]),
        ]
        result = await plan_tools.create(make_create_req("chain", tasks))

        assert result.execution_levels == 3
        assert result.execution_order == [["a"], ["b"], ["c"]]

    @pytest.mark.asyncio
    async def test_create_parallel_branches(self, plan_tools):
        """Tasks with no mutual dependencies are in the same level."""
        tasks = [
            make_task("root"),
            make_task("b1", depends_on=["root"]),
            make_task("b2", depends_on=["root"]),
            make_task("end", depends_on=["b1", "b2"]),
        ]
        result = await plan_tools.create(make_create_req("parallel", tasks))

        assert result.execution_levels == 3
        # root is level 0, b1/b2 level 1 (sorted), end level 2
        assert result.execution_order[0] == ["root"]
        assert sorted(result.execution_order[1]) == ["b1", "b2"]
        assert result.execution_order[2] == ["end"]

    @pytest.mark.asyncio
    async def test_create_empty_tasks_raises(self, plan_tools):
        from anyide.modules.plan.tools import PlanValidationError

        with pytest.raises(PlanValidationError, match="at least one task"):
            await plan_tools.create(make_create_req("empty", []))

    @pytest.mark.asyncio
    async def test_create_cycle_raises(self, plan_tools):
        """A → B → A is a cycle."""
        from anyide.modules.plan.tools import PlanValidationError

        tasks = [
            make_task("a", depends_on=["b"]),
            make_task("b", depends_on=["a"]),
        ]
        with pytest.raises(PlanValidationError, match="Cycle"):
            await plan_tools.create(make_create_req("cycle", tasks))

    @pytest.mark.asyncio
    async def test_create_self_loop_raises(self, plan_tools):
        from anyide.modules.plan.tools import PlanValidationError

        tasks = [make_task("a", depends_on=["a"])]
        with pytest.raises(PlanValidationError):
            await plan_tools.create(make_create_req("selfloop", tasks))

    @pytest.mark.asyncio
    async def test_create_unknown_dependency_raises(self, plan_tools):
        from anyide.modules.plan.tools import PlanValidationError

        tasks = [make_task("a", depends_on=["nonexistent"])]
        with pytest.raises(PlanValidationError, match="unknown task"):
            await plan_tools.create(make_create_req("missing_dep", tasks))

    @pytest.mark.asyncio
    async def test_create_duplicate_task_ids_raises(self, plan_tools):
        from anyide.modules.plan.tools import PlanValidationError

        tasks = [make_task("a"), make_task("a")]
        with pytest.raises(PlanValidationError, match="Duplicate"):
            await plan_tools.create(make_create_req("dup", tasks))

    @pytest.mark.asyncio
    async def test_create_invalid_on_failure_raises(self, plan_tools):
        from anyide.modules.plan.tools import PlanValidationError

        tasks = [make_task("a")]
        req = make_create_req("bad_policy", tasks, on_failure="invalid_policy")
        with pytest.raises(PlanValidationError, match="Invalid on_failure"):
            await plan_tools.create(req)

    @pytest.mark.asyncio
    async def test_create_persists_to_db(self, plan_tools, plan_db):
        """Created plan and tasks should be in the DB."""
        req = make_create_req("persist", [make_task("p1"), make_task("p2", depends_on=["p1"])])
        result = await plan_tools.create(req)

        conn = plan_db.connection
        cur = await conn.execute("SELECT * FROM plan_plans WHERE id = ?", (result.plan_id,))
        plan_row = await cur.fetchone()
        assert plan_row is not None
        assert plan_row["name"] == "persist"
        assert plan_row["status"] == "pending"

        cur = await conn.execute("SELECT COUNT(*) as cnt FROM plan_tasks WHERE plan_id = ?", (result.plan_id,))
        count = (await cur.fetchone())["cnt"]
        assert count == 2


# ---------------------------------------------------------------------------
# TestPlanExecute — success paths
# ---------------------------------------------------------------------------


class TestPlanExecuteSuccess:
    """Tests for plan_execute — success scenarios."""

    @pytest.mark.asyncio
    async def test_execute_single_task(self, plan_db):
        """Single task plan should complete and record output."""
        call_log = []

        async def dispatch(category, name, params):
            call_log.append((category, name, params))
            return {"result": "hello"}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        create_req = make_create_req("single_exec", [make_task("t1", tool_cat="shell", tool_name="execute")])
        created = await pt.create(create_req)

        from anyide.models import PlanExecuteRequest

        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.status == "completed"
        assert result.tasks_completed == 1
        assert result.tasks_failed == 0
        assert result.tasks_skipped == 0
        assert len(call_log) == 1
        assert call_log[0] == ("shell", "execute", {})

    @pytest.mark.asyncio
    async def test_execute_sequential_chain_order(self, plan_db):
        """Tasks in a chain must execute in dependency order."""
        call_order = []

        async def dispatch(category, name, params):
            call_order.append(name)
            return {"step": name}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        tasks = [
            make_task("s1", tool_name="step1"),
            make_task("s2", tool_name="step2", depends_on=["s1"]),
            make_task("s3", tool_name="step3", depends_on=["s2"]),
        ]
        created = await pt.create(make_create_req("chain_exec", tasks))

        from anyide.models import PlanExecuteRequest

        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.status == "completed"
        assert result.tasks_completed == 3
        assert call_order == ["step1", "step2", "step3"]

    @pytest.mark.asyncio
    async def test_execute_parallel_branches_run_concurrently(self, plan_db):
        """Tasks in same level should all be dispatched (concurrent via gather)."""
        called = []

        async def dispatch(category, name, params):
            called.append(name)
            return {"done": name}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        tasks = [
            make_task("root", tool_name="root"),
            make_task("b1", tool_name="branch1", depends_on=["root"]),
            make_task("b2", tool_name="branch2", depends_on=["root"]),
            make_task("end", tool_name="end", depends_on=["b1", "b2"]),
        ]
        created = await pt.create(make_create_req("parallel_exec", tasks))

        from anyide.models import PlanExecuteRequest

        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.status == "completed"
        assert result.tasks_completed == 4
        # root first, then both branches (order within level not guaranteed), then end
        assert called[0] == "root"
        assert "branch1" in called
        assert "branch2" in called
        assert called[-1] == "end"

    @pytest.mark.asyncio
    async def test_execute_task_ref_resolution(self, plan_db):
        """{{task:ID.field}} in params should be resolved before dispatch."""
        dispatched_params = []

        async def dispatch(category, name, params):
            dispatched_params.append(params)
            return {"output_value": "resolved_data"}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        tasks = [
            make_task("producer", tool_name="first", params={}),
            make_task("consumer", tool_name="second", params={"input": "{{task:producer.output_value}}"}, depends_on=["producer"]),
        ]
        created = await pt.create(make_create_req("ref_resolve", tasks))

        from anyide.models import PlanExecuteRequest

        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.status == "completed"
        # Consumer should receive resolved value
        consumer_params = dispatched_params[1]
        assert consumer_params["input"] == "resolved_data"

    @pytest.mark.asyncio
    async def test_execute_resolves_unique_plan_name_reference(self, plan_db):
        """If plan_id is a unique plan name, execute should resolve it."""
        async def dispatch(category, name, params):
            return {"ok": True}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest

        created = await pt.create(make_create_req("plan_name_ref", [make_task("t1")]))
        result = await pt.execute(PlanExecuteRequest(plan_id="plan_name_ref"))

        assert result.status == "completed"
        assert result.plan_id == created.plan_id

    @pytest.mark.asyncio
    async def test_execute_waits_briefly_for_concurrent_plan_create_by_name(self, plan_db):
        """If execute races create, a brief retry window should resolve by name."""
        async def dispatch(category, name, params):
            return {"ok": True}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest

        async def delayed_create():
            await asyncio.sleep(0.15)
            return await pt.create(make_create_req("race_plan_name", [make_task("t1")]))

        create_task = asyncio.create_task(delayed_create())
        result = await pt.execute(PlanExecuteRequest(plan_id="race_plan_name"))
        created = await create_task

        assert result.status == "completed"
        assert result.plan_id == created.plan_id


# ---------------------------------------------------------------------------
# TestPlanExecuteFailurePolicies
# ---------------------------------------------------------------------------


class TestPlanExecuteFailurePolicies:
    """Tests for plan_execute — failure policy handling."""

    @pytest.mark.asyncio
    async def test_failure_stop_policy(self, plan_db):
        """When on_failure=stop, failure of one task stops remaining tasks."""
        call_count = [0]

        async def dispatch(category, name, params):
            call_count[0] += 1
            if name == "fail_me":
                raise RuntimeError("Simulated failure")
            return {"ok": True}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        # fail_me and ok_task at same level; after_fail depends on both
        tasks = [
            make_task("fail_me", tool_name="fail_me"),
            make_task("ok_task", tool_name="ok_task"),
            make_task("after_fail", tool_name="after_fail", depends_on=["fail_me", "ok_task"]),
        ]
        created = await pt.create(make_create_req("stop_policy", tasks, on_failure="stop"))

        from anyide.models import PlanExecuteRequest, PlanStatusRequest

        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))
        status = await pt.status(PlanStatusRequest(plan_id=created.plan_id))

        assert result.status == "failed"
        assert result.tasks_failed >= 1
        assert result.tasks_skipped >= 1

        # after_fail should be skipped
        task_statuses = {t.id: t.status for t in status.tasks}
        assert task_statuses["fail_me"] == "failed"
        assert task_statuses["after_fail"] == "skipped"

    @pytest.mark.asyncio
    async def test_failure_skip_dependents_policy(self, plan_db):
        """skip_dependents: only skip tasks that depend on the failed task."""
        called = []

        async def dispatch(category, name, params):
            called.append(name)
            if name == "fail_me":
                raise RuntimeError("fail")
            return {"ok": True}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        # fail_me and independent at same level; dep_on_fail depends only on fail_me
        tasks = [
            make_task("fail_me", tool_name="fail_me"),
            make_task("independent", tool_name="independent"),
            make_task("dep_on_fail", tool_name="dep_on_fail", depends_on=["fail_me"]),
        ]
        created = await pt.create(make_create_req("skip_deps", tasks, on_failure="skip_dependents"))

        from anyide.models import PlanExecuteRequest, PlanStatusRequest

        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))
        status = await pt.status(PlanStatusRequest(plan_id=created.plan_id))

        task_statuses = {t.id: t.status for t in status.tasks}
        assert task_statuses["fail_me"] == "failed"
        assert task_statuses["dep_on_fail"] == "skipped"
        # independent task should still run and complete
        assert task_statuses["independent"] == "completed"
        assert "independent" in called

    @pytest.mark.asyncio
    async def test_failure_continue_policy(self, plan_db):
        """continue policy: all tasks run regardless of failures."""
        called = []

        async def dispatch(category, name, params):
            called.append(name)
            if name == "fail_me":
                raise RuntimeError("fail")
            return {"ok": True}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        tasks = [
            make_task("fail_me", tool_name="fail_me"),
            make_task("after_fail", tool_name="after_fail", depends_on=["fail_me"]),
        ]
        created = await pt.create(make_create_req("continue_policy", tasks, on_failure="continue"))

        from anyide.models import PlanExecuteRequest, PlanStatusRequest

        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))
        status = await pt.status(PlanStatusRequest(plan_id=created.plan_id))

        task_statuses = {t.id: t.status for t in status.tasks}
        assert task_statuses["fail_me"] == "failed"
        # after_fail should run (continue policy)
        assert task_statuses["after_fail"] == "completed"
        assert "after_fail" in called

    @pytest.mark.asyncio
    async def test_per_task_on_failure_override(self, plan_db):
        """Per-task on_failure overrides plan-level policy."""
        called = []

        async def dispatch(category, name, params):
            called.append(name)
            if name == "fail_me":
                raise RuntimeError("fail")
            return {"ok": True}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        # Plan is stop, but fail_me has continue override
        tasks = [
            make_task("fail_me", tool_name="fail_me", on_failure="continue"),
            make_task("after", tool_name="after", depends_on=["fail_me"]),
        ]
        created = await pt.create(make_create_req("per_task_override", tasks, on_failure="stop"))

        from anyide.models import PlanExecuteRequest, PlanStatusRequest

        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))
        status = await pt.status(PlanStatusRequest(plan_id=created.plan_id))

        task_statuses = {t.id: t.status for t in status.tasks}
        # With continue override, after should still run
        assert task_statuses["after"] == "completed"


# ---------------------------------------------------------------------------
# TestPlanExecuteNotFound
# ---------------------------------------------------------------------------


class TestPlanExecuteNotFound:
    @pytest.mark.asyncio
    async def test_execute_nonexistent_plan(self, plan_tools):
        from anyide.models import PlanExecuteRequest
        from anyide.modules.plan.tools import PlanNotFoundError

        with pytest.raises(PlanNotFoundError):
            await plan_tools.execute(PlanExecuteRequest(plan_id="does-not-exist"))

    @pytest.mark.asyncio
    async def test_execute_plan_name_ambiguous_raises_value_error(self, plan_tools):
        """Name fallback should fail when multiple plans share the same name."""
        from anyide.models import PlanExecuteRequest

        await plan_tools.create(make_create_req("duplicate_name", [make_task("a1")]))
        await plan_tools.create(make_create_req("duplicate_name", [make_task("a2")]))

        with pytest.raises(ValueError, match="Multiple plans named"):
            await plan_tools.execute(PlanExecuteRequest(plan_id="duplicate_name"))

    @pytest.mark.asyncio
    async def test_execute_already_completed(self, plan_db):
        """Re-executing a completed plan should raise ValueError."""
        async def dispatch(category, name, params):
            return {"ok": True}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest

        created = await pt.create(make_create_req("rerun", [make_task("t1")]))
        await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        with pytest.raises(ValueError, match="already finished"):
            await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))


# ---------------------------------------------------------------------------
# TestPlanStatus
# ---------------------------------------------------------------------------


class TestPlanStatus:
    @pytest.mark.asyncio
    async def test_status_pending_plan(self, plan_tools):
        from anyide.models import PlanStatusRequest

        created = await plan_tools.create(make_create_req("pending", [make_task("x1"), make_task("x2")]))
        status = await plan_tools.status(PlanStatusRequest(plan_id=created.plan_id))

        assert status.plan_id == created.plan_id
        assert status.name == "pending"
        assert status.status == "pending"
        assert status.tasks_total == 2
        assert status.tasks_completed == 0
        assert status.tasks_failed == 0
        assert status.tasks_running == 0

    @pytest.mark.asyncio
    async def test_status_completed_plan(self, plan_db):
        async def dispatch(category, name, params):
            return {"value": 42}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest, PlanStatusRequest

        created = await pt.create(make_create_req("done", [make_task("q1"), make_task("q2", depends_on=["q1"])]))
        await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))
        status = await pt.status(PlanStatusRequest(plan_id=created.plan_id))

        assert status.status == "completed"
        assert status.tasks_completed == 2
        assert status.tasks_failed == 0

        # Check output is preserved
        task_map = {t.id: t for t in status.tasks}
        assert task_map["q1"].output == {"value": 42}
        assert task_map["q1"].status == "completed"

    @pytest.mark.asyncio
    async def test_status_task_timestamps(self, plan_db):
        async def dispatch(category, name, params):
            return {}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest, PlanStatusRequest

        created = await pt.create(make_create_req("timestamps", [make_task("ts1")]))
        await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))
        status = await pt.status(PlanStatusRequest(plan_id=created.plan_id))

        task = status.tasks[0]
        assert task.started_at is not None
        assert task.completed_at is not None
        assert status.started_at is not None
        assert status.completed_at is not None

    @pytest.mark.asyncio
    async def test_status_not_found(self, plan_tools):
        from anyide.models import PlanStatusRequest
        from anyide.modules.plan.tools import PlanNotFoundError

        with pytest.raises(PlanNotFoundError):
            await plan_tools.status(PlanStatusRequest(plan_id="no-such-plan"))


# ---------------------------------------------------------------------------
# TestPlanList
# ---------------------------------------------------------------------------


class TestPlanList:
    @pytest.mark.asyncio
    async def test_list_empty(self, plan_tools):
        result = await plan_tools.list()
        assert result.total == 0
        assert result.plans == []

    @pytest.mark.asyncio
    async def test_list_multiple_plans(self, plan_tools):
        await plan_tools.create(make_create_req("alpha", [make_task("a1")]))
        await plan_tools.create(make_create_req("beta", [make_task("b1"), make_task("b2")]))

        result = await plan_tools.list()
        assert result.total == 2

        names = {p.name for p in result.plans}
        assert "alpha" in names
        assert "beta" in names

        task_counts = {p.name: p.task_count for p in result.plans}
        assert task_counts["alpha"] == 1
        assert task_counts["beta"] == 2

    @pytest.mark.asyncio
    async def test_list_shows_status(self, plan_db):
        async def dispatch(category, name, params):
            return {}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest

        created = await pt.create(make_create_req("finished", [make_task("f1")]))
        await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        listing = await pt.list()
        assert listing.total == 1
        assert listing.plans[0].status == "completed"


# ---------------------------------------------------------------------------
# TestPlanCancel
# ---------------------------------------------------------------------------


class TestPlanCancel:
    @pytest.mark.asyncio
    async def test_cancel_pending_plan(self, plan_tools):
        from anyide.models import PlanCancelRequest, PlanStatusRequest

        created = await plan_tools.create(make_create_req("to_cancel", [make_task("c1"), make_task("c2")]))
        cancel_result = await plan_tools.cancel(PlanCancelRequest(plan_id=created.plan_id))

        assert cancel_result.status == "cancelled"
        assert cancel_result.cancelled_tasks == 2

        status = await plan_tools.status(PlanStatusRequest(plan_id=created.plan_id))
        assert status.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_raises(self, plan_tools):
        from anyide.models import PlanCancelRequest

        created = await plan_tools.create(make_create_req("cancel2", [make_task("d1")]))
        await plan_tools.cancel(PlanCancelRequest(plan_id=created.plan_id))

        with pytest.raises(ValueError, match="already 'cancelled'"):
            await plan_tools.cancel(PlanCancelRequest(plan_id=created.plan_id))

    @pytest.mark.asyncio
    async def test_cancel_completed_plan_raises(self, plan_db):
        async def dispatch(category, name, params):
            return {}

        pt = _make_plan_tools(plan_db, dispatch=dispatch)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanCancelRequest, PlanExecuteRequest

        created = await pt.create(make_create_req("done_cancel", [make_task("e1")]))
        await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        with pytest.raises(ValueError, match="already 'completed'"):
            await pt.cancel(PlanCancelRequest(plan_id=created.plan_id))

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, plan_tools):
        from anyide.models import PlanCancelRequest
        from anyide.modules.plan.tools import PlanNotFoundError

        with pytest.raises(PlanNotFoundError):
            await plan_tools.cancel(PlanCancelRequest(plan_id="ghost-plan"))


# ---------------------------------------------------------------------------
# TestPlanHITL
# ---------------------------------------------------------------------------


class TestPlanHITL:
    """Tests for HITL integration within plan tasks."""

    @pytest.mark.asyncio
    async def test_hitl_approved_task_runs(self, plan_db):
        """Tasks with require_hitl=True run when HITL approves."""
        called = []

        async def dispatch(category, name, params):
            called.append(name)
            return {"done": True}

        # Mock HITL that approves
        mock_hitl_req = MagicMock()
        mock_hitl_req.id = "hitl-req-1"

        mock_hitl = MagicMock()
        mock_hitl.create_request = AsyncMock(return_value=mock_hitl_req)
        mock_hitl.wait_for_decision = AsyncMock(return_value="approved")

        pt = _make_plan_tools(plan_db, dispatch=dispatch, hitl=mock_hitl)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest

        created = await pt.create(make_create_req("hitl_approved", [make_task("h1", require_hitl=True)]))
        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.status == "completed"
        assert result.tasks_completed == 1
        assert "read" in called  # default tool_name

        mock_hitl.create_request.assert_called_once()
        mock_hitl.wait_for_decision.assert_called_once_with("hitl-req-1")

    @pytest.mark.asyncio
    async def test_hitl_rejected_task_fails(self, plan_db):
        """Tasks with require_hitl=True fail when HITL rejects."""
        mock_hitl_req = MagicMock()
        mock_hitl_req.id = "hitl-req-2"

        mock_hitl = MagicMock()
        mock_hitl.create_request = AsyncMock(return_value=mock_hitl_req)
        mock_hitl.wait_for_decision = AsyncMock(return_value="rejected")

        async def dispatch(category, name, params):
            return {}

        pt = _make_plan_tools(plan_db, dispatch=dispatch, hitl=mock_hitl)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest, PlanStatusRequest

        created = await pt.create(make_create_req("hitl_rejected", [make_task("h2", require_hitl=True)]))
        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.status == "failed"
        assert result.tasks_failed == 1

        status = await pt.status(PlanStatusRequest(plan_id=created.plan_id))
        assert status.tasks[0].error == "Task rejected via HITL"

    @pytest.mark.asyncio
    async def test_hitl_expired_task_fails(self, plan_db):
        """Tasks with require_hitl=True fail when HITL expires."""
        mock_hitl_req = MagicMock()
        mock_hitl_req.id = "hitl-req-3"

        mock_hitl = MagicMock()
        mock_hitl.create_request = AsyncMock(return_value=mock_hitl_req)
        mock_hitl.wait_for_decision = AsyncMock(return_value="expired")

        async def dispatch(category, name, params):
            return {}

        pt = _make_plan_tools(plan_db, dispatch=dispatch, hitl=mock_hitl)
        conn = plan_db.connection
        await conn.execute("DELETE FROM plan_tasks")
        await conn.execute("DELETE FROM plan_plans")
        await conn.commit()

        from anyide.models import PlanExecuteRequest, PlanStatusRequest

        created = await pt.create(make_create_req("hitl_expired", [make_task("h3", require_hitl=True)]))
        result = await pt.execute(PlanExecuteRequest(plan_id=created.plan_id))

        assert result.status == "failed"
        status = await pt.status(PlanStatusRequest(plan_id=created.plan_id))
        assert status.tasks[0].error == "HITL approval timed out"


# ---------------------------------------------------------------------------
# TestHelperFunctions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Unit tests for standalone helper functions."""

    def test_compute_execution_levels_linear(self):
        from anyide.modules.plan.tools import _compute_execution_levels

        tasks = [
            {"id": "a", "depends_on": []},
            {"id": "b", "depends_on": ["a"]},
            {"id": "c", "depends_on": ["b"]},
        ]
        levels = _compute_execution_levels(tasks)
        assert levels == [["a"], ["b"], ["c"]]

    def test_compute_execution_levels_parallel(self):
        from anyide.modules.plan.tools import _compute_execution_levels

        tasks = [
            {"id": "root", "depends_on": []},
            {"id": "x", "depends_on": ["root"]},
            {"id": "y", "depends_on": ["root"]},
        ]
        levels = _compute_execution_levels(tasks)
        assert levels[0] == ["root"]
        assert sorted(levels[1]) == ["x", "y"]

    def test_compute_execution_levels_detects_cycle(self):
        from anyide.modules.plan.tools import PlanValidationError, _compute_execution_levels

        tasks = [
            {"id": "a", "depends_on": ["b"]},
            {"id": "b", "depends_on": ["a"]},
        ]
        with pytest.raises(PlanValidationError, match="Cycle"):
            _compute_execution_levels(tasks)

    def test_compute_execution_levels_detects_missing_dep(self):
        from anyide.modules.plan.tools import PlanValidationError, _compute_execution_levels

        tasks = [{"id": "a", "depends_on": ["ghost"]}]
        with pytest.raises(PlanValidationError, match="unknown task"):
            _compute_execution_levels(tasks)

    def test_get_transitive_dependents(self):
        from anyide.modules.plan.tools import _get_transitive_dependents

        tasks = [
            {"id": "a", "depends_on": "[]"},
            {"id": "b", "depends_on": '["a"]'},
            {"id": "c", "depends_on": '["b"]'},
            {"id": "d", "depends_on": "[]"},  # unrelated
        ]
        deps = _get_transitive_dependents("a", tasks)
        assert "b" in deps
        assert "c" in deps
        assert "d" not in deps
        assert "a" not in deps

    def test_resolve_task_refs_simple(self):
        from anyide.modules.plan.tools import _resolve_task_refs

        params = {"input": "{{task:t1.value}}"}
        outputs = {"t1": {"value": "hello"}}
        resolved = _resolve_task_refs(params, outputs)
        assert resolved["input"] == "hello"

    def test_resolve_task_refs_missing_task(self):
        from anyide.modules.plan.tools import _resolve_task_refs

        params = {"input": "{{task:missing.field}}"}
        resolved = _resolve_task_refs(params, {})
        assert resolved["input"] == ""  # defaults to empty string

    def test_resolve_task_refs_nested(self):
        from anyide.modules.plan.tools import _resolve_task_refs

        params = {"a": "{{task:t1.x}}", "b": "{{task:t2.y}}"}
        outputs = {"t1": {"x": "foo"}, "t2": {"y": "bar"}}
        resolved = _resolve_task_refs(params, outputs)
        assert resolved["a"] == "foo"
        assert resolved["b"] == "bar"

    def test_resolve_task_refs_dict_value(self):
        from anyide.modules.plan.tools import _resolve_task_refs

        params = {"data": "{{task:t1.nested}}"}
        outputs = {"t1": {"nested": {"key": "val"}}}
        resolved = _resolve_task_refs(params, outputs)
        # When the entire string value is a reference, the original type is preserved
        assert resolved["data"] == {"key": "val"}


# ---------------------------------------------------------------------------
# TestPlanIntegration — HTTP API layer
# ---------------------------------------------------------------------------


def _api_client():
    """Return a started TestClient context manager."""
    from fastapi.testclient import TestClient
    from anyide.main import app

    return TestClient(app, raise_server_exceptions=False)


def _api_create_plan(client, name, tasks, on_failure="stop"):
    """Helper to create a plan via the root API endpoint."""
    return client.post(
        "/api/tools/plan/create",
        json={"name": name, "tasks": tasks, "on_failure": on_failure},
    )


class TestPlanIntegration:
    """Integration tests using FastAPI TestClient via plan endpoints."""

    def test_create_plan_api(self):
        tasks = [{"id": "t1", "name": "Task 1", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": []}]
        with _api_client() as client:
            resp = _api_create_plan(client, "api_test", tasks)
        assert resp.status_code == 200
        data = resp.json()
        assert "plan_id" in data
        assert data["task_count"] == 1
        assert data["execution_levels"] == 1

    def test_create_plan_cycle_returns_422(self):
        tasks = [
            {"id": "a", "name": "A", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": ["b"]},
            {"id": "b", "name": "B", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": ["a"]},
        ]
        with _api_client() as client:
            resp = _api_create_plan(client, "cycle_api", tasks)
        assert resp.status_code == 422

    def test_plan_status_not_found_returns_404(self):
        with _api_client() as client:
            resp = client.post("/api/tools/plan/status", json={"plan_id": "nonexistent-id-xyz"})
        assert resp.status_code == 404

    def test_plan_list_api(self):
        with _api_client() as client:
            resp = client.post("/api/tools/plan/list", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "plans" in data
        assert "total" in data

    def test_plan_cancel_not_found_returns_404(self):
        with _api_client() as client:
            resp = client.post("/api/tools/plan/cancel", json={"plan_id": "nonexistent-id-xyz"})
        assert resp.status_code == 404

    def test_create_then_status_via_api(self):
        """Create a plan and immediately check status."""
        tasks = [
            {"id": "s1", "name": "Step 1", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": []},
            {"id": "s2", "name": "Step 2", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": ["s1"]},
        ]
        with _api_client() as client:
            create_resp = _api_create_plan(client, "status_check", tasks)
            assert create_resp.status_code == 200
            plan_id = create_resp.json()["plan_id"]

            status_resp = client.post("/api/tools/plan/status", json={"plan_id": plan_id})
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["plan_id"] == plan_id
        assert data["status"] == "pending"
        assert data["tasks_total"] == 2
        assert len(data["tasks"]) == 2

    def test_execute_by_unique_plan_name_via_api(self):
        """Execute endpoint should resolve unique plan names and return canonical plan_id."""
        tasks = [{"id": "e1", "name": "E1", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": []}]
        with _api_client() as client:
            create_resp = _api_create_plan(client, "execute_by_name_api", tasks)
            assert create_resp.status_code == 200
            created_plan_id = create_resp.json()["plan_id"]

            exec_resp = client.post("/api/tools/plan/execute", json={"plan_id": "execute_by_name_api"})
        assert exec_resp.status_code == 200
        data = exec_resp.json()
        assert data["plan_id"] == created_plan_id
        assert data["status"] in ("completed", "failed")

    def test_create_then_cancel_via_api(self):
        """Create a plan and cancel it via API."""
        tasks = [{"id": "c1", "name": "C1", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": []}]
        with _api_client() as client:
            create_resp = _api_create_plan(client, "cancel_test_api", tasks)
            assert create_resp.status_code == 200
            plan_id = create_resp.json()["plan_id"]

            cancel_resp = client.post("/api/tools/plan/cancel", json={"plan_id": plan_id})
        assert cancel_resp.status_code == 200
        data = cancel_resp.json()
        assert data["status"] == "cancelled"
        assert data["cancelled_tasks"] == 1

    def test_sub_app_create_endpoint(self):
        """Sub-app endpoint /tools/plan/create should also work."""
        tasks = [{"id": "sub1", "name": "Sub 1", "tool_category": "fs", "tool_name": "read", "params": {}, "depends_on": []}]
        with _api_client() as client:
            resp = client.post("/tools/plan/create", json={"name": "sub_app_test", "tasks": tasks})
        assert resp.status_code == 200
        assert "plan_id" in resp.json()

    def test_sub_app_list_endpoint(self):
        with _api_client() as client:
            resp = client.post("/tools/plan/list", json={})
        assert resp.status_code == 200

    def test_sub_app_status_not_found(self):
        # Sub-apps don't have exception handlers, so not-found returns 500
        with _api_client() as client:
            resp = client.post("/tools/plan/status", json={"plan_id": "ghost-id"})
        assert resp.status_code in (404, 500)
