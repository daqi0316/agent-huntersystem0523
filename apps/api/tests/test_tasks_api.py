"""Tests for app/api/tasks.py — LangGraph task orchestration endpoints.

覆盖 create_task / list_tasks / get_task / task_timeline / task_snapshots
以及 _get_graph 单例 + 异常路径。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.tasks import _get_graph, router as tasks_router
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.models.operation_log import OperationStatus


# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def fake_user_id() -> str:
    return "user-1"


@pytest.fixture
def app(fake_user_id: str) -> FastAPI:
    app = FastAPI()
    app.include_router(tasks_router, prefix="/tasks")
    app.dependency_overrides[get_current_user_id] = lambda: fake_user_id
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _patch_db(app: FastAPI, db_mock):
    """Override get_db dependency to return mock session."""

    async def fake_get_db():
        yield db_mock

    app.dependency_overrides[get_db] = fake_get_db


def _make_op_log(
    id: str = "op1",
    agent_name: str = "router",
    action: str = "classify",
    status_value: OperationStatus = OperationStatus.COMPLETED,
    created_at: datetime | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    duration_ms: int | None = 42,
) -> MagicMock:
    op = MagicMock()
    op.id = id
    op.agent_name = agent_name
    op.action = action
    op.status = status_value
    op.created_at = created_at or datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
    op.input_summary = input_summary
    op.output_summary = output_summary
    op.duration_ms = duration_ms
    return op


# ─── create_task (POST /tasks) ────────────────────────────────────────


class TestCreateTask:
    def test_success(self, client: TestClient) -> None:
        """graph.ainvoke 返回完整 state → 包装 success 响应."""
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(
            return_value={
                "intent": "search_candidates",
                "status": "completed",
                "agent_result": {"found": 3},
                "error": None,
            }
        )
        with patch("app.api.tasks._get_graph", return_value=fake_graph):
            resp = client.post("/tasks", params={"input_text": "find python devs", "job_id": "j1"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["intent"] == "search_candidates"
        assert body["data"]["status"] == "completed"
        assert body["data"]["agent_result"] == {"found": 3}
        assert body["data"]["error"] is None
        # task_id 是 uuid
        assert isinstance(body["data"]["task_id"], str) and len(body["data"]["task_id"]) == 36

    def test_invoke_exception_returns_500(self, client: TestClient) -> None:
        """graph.ainvoke 抛异常 → error 500."""
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))
        with patch("app.api.tasks._get_graph", return_value=fake_graph):
            resp = client.post("/tasks", params={"input_text": "test"})

        assert resp.status_code == 500
        assert "Task execution failed" in resp.json()["error"]
        assert "LLM timeout" in resp.json()["error"]

    def test_invoke_passes_configurable_thread_id(self, client: TestClient) -> None:
        """thread_id 应等于 task_id."""
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(return_value={"intent": "x", "status": "ok"})
        with patch("app.api.tasks._get_graph", return_value=fake_graph) as mock_get:
            client.post("/tasks", params={"input_text": "x"})
        # 验证 _get_graph 被调用
        assert mock_get.called
        # 验证 ainvoke 的 config 包含 thread_id
        call_args = fake_graph.ainvoke.call_args
        config = call_args.kwargs["config"]
        assert "configurable" in config
        thread_id = config["configurable"]["thread_id"]
        # thread_id 应是合法 uuid
        assert isinstance(thread_id, str) and len(thread_id) == 36

    def test_initial_state_has_all_keys(self, client: TestClient) -> None:
        """传给 ainvoke 的 state dict 应包含所有 graph 期望的 key."""
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(return_value={"intent": "x"})
        with patch("app.api.tasks._get_graph", return_value=fake_graph):
            client.post("/tasks", params={"input_text": "hello", "job_id": "job-9"})

        state = fake_graph.ainvoke.call_args.args[0]
        assert state["input_text"] == "hello"
        assert state["job_id"] == "job-9"
        assert state["user_id"] == "user-1"
        assert state["intent"] == ""
        assert state["agent_result"] is None
        assert state["error"] is None
        assert state["status"] == ""
        assert "task_id" in state


# ─── list_tasks (GET /tasks) ─────────────────────────────────────────


class TestListTasks:
    def test_success(self, app: FastAPI) -> None:
        """正常返回 task 列表 + 分页信息."""
        db = MagicMock()
        result = MagicMock()
        row1 = SimpleNamespace(
            task_id="t1", last_event_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            last_action="search", last_agent="router",
        )
        row2 = SimpleNamespace(
            task_id="t2", last_event_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
            last_action="screen", last_agent="screener",
        )
        result.all = MagicMock(return_value=[row1, row2])
        db.execute = AsyncMock(return_value=result)
        _patch_db(app, db)

        resp = TestClient(app).get("/tasks", params={"skip": 0, "limit": 20})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["count"] == 2
        assert data["skip"] == 0
        assert data["limit"] == 20
        assert len(data["tasks"]) == 2
        assert data["tasks"][0]["task_id"] == "t1"
        assert data["tasks"][0]["last_action"] == "search"
        assert data["tasks"][0]["last_agent"] == "router"
        assert data["tasks"][1]["task_id"] == "t2"

    def test_empty_result(self, app: FastAPI) -> None:
        """无任务 → count=0 + 空数组."""
        db = MagicMock()
        result = MagicMock()
        result.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=result)
        _patch_db(app, db)

        resp = TestClient(app).get("/tasks")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["count"] == 0
        assert data["tasks"] == []

    def test_null_last_event_at(self, app: FastAPI) -> None:
        """last_event_at 为 None → ISO 字段是空字符串."""
        db = MagicMock()
        result = MagicMock()
        row = SimpleNamespace(
            task_id="t1", last_event_at=None,
            last_action="x", last_agent="y",
        )
        result.all = MagicMock(return_value=[row])
        db.execute = AsyncMock(return_value=result)
        _patch_db(app, db)

        resp = TestClient(app).get("/tasks")

        assert resp.status_code == 200
        task = resp.json()["data"]["tasks"][0]
        assert task["last_event_at"] == ""

    def test_pagination_params(self, app: FastAPI) -> None:
        """skip/limit 透传到响应."""
        db = MagicMock()
        result = MagicMock()
        result.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=result)
        _patch_db(app, db)

        resp = TestClient(app).get("/tasks", params={"skip": 10, "limit": 50})

        data = resp.json()["data"]
        assert data["skip"] == 10
        assert data["limit"] == 50


# ─── get_task (GET /tasks/{task_id}) ──────────────────────────────────


class TestGetTask:
    def test_success(self, app: FastAPI) -> None:
        """返回 20 条最近事件."""
        op1 = _make_op_log(id="op1", agent_name="router", action="classify")
        op2 = _make_op_log(id="op2", agent_name="searcher", action="search")
        db = MagicMock()
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[op1, op2])))
        db.execute = AsyncMock(return_value=result)
        _patch_db(app, db)

        resp = TestClient(app).get("/tasks/task-1")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["task_id"] == "task-1"
        assert len(data["events"]) == 2
        assert data["events"][0]["agent_name"] == "router"
        assert data["events"][0]["action"] == "classify"
        assert data["events"][0]["status"] == "completed"

    def test_empty_events(self, app: FastAPI) -> None:
        db = MagicMock()
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=result)
        _patch_db(app, db)

        resp = TestClient(app).get("/tasks/nonexistent")

        assert resp.status_code == 200
        assert resp.json()["data"]["events"] == []


# ─── task_timeline (GET /tasks/{task_id}/timeline) ────────────────────


class TestTaskTimeline:
    def test_success_with_output_summary(self, app: FastAPI) -> None:
        """优先用 output_summary, 否则用 input_summary."""
        op1 = _make_op_log(
            output_summary="found 3 candidates",
            input_summary=None,
            duration_ms=120,
        )
        op2 = _make_op_log(
            output_summary=None,
            input_summary="search: python devs",
            duration_ms=None,
        )
        db = MagicMock()
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[op1, op2])))
        db.execute = AsyncMock(return_value=result)
        _patch_db(app, db)

        resp = TestClient(app).get("/tasks/task-1/timeline")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert data["events"][0]["summary"] == "found 3 candidates"
        assert data["events"][0]["duration_ms"] == 120
        assert data["events"][1]["summary"] == "search: python devs"

    def test_both_summaries_empty(self, app: FastAPI) -> None:
        """output 和 input 都为 None → summary 字段是空字符串."""
        op = _make_op_log(output_summary=None, input_summary=None)
        db = MagicMock()
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[op])))
        db.execute = AsyncMock(return_value=result)
        _patch_db(app, db)

        resp = TestClient(app).get("/tasks/task-1/timeline")

        assert resp.json()["data"]["events"][0]["summary"] == ""


# ─── task_snapshots (GET /tasks/{task_id}/snapshots) ──────────────────


class TestTaskSnapshots:
    def test_success(self) -> None:
        """从 graph.get_state_history 读 snapshots."""
        state = SimpleNamespace(
            values={"intent": "search", "status": "running", "error": None},
            metadata={"step": 1, "source": "loop"},
            next=("node_a",),
            config={"configurable": {"checkpoint_id": "cp-123"}},
        )
        fake_graph = MagicMock()
        fake_graph.get_state_history = MagicMock(return_value=iter([state]))

        with patch("app.api.tasks._get_graph", return_value=fake_graph):
            import asyncio
            from app.api.tasks import task_snapshots
            result = asyncio.run(task_snapshots(task_id="t1"))

        assert result["success"] is True
        snapshots = result["data"]["snapshots"]
        assert snapshots[0]["step"] == 1
        assert snapshots[0]["intent"] == "search"
        assert snapshots[0]["status"] == "running"
        assert snapshots[0]["checkpoint_id"] == "cp-123"
        assert snapshots[0]["next"] == ["node_a"]

    def test_history_failure_returns_empty(self) -> None:
        """get_state_history 抛异常 → 容错返回空数组."""
        fake_graph = MagicMock()
        fake_graph.get_state_history = MagicMock(side_effect=RuntimeError("checkpoint evicted"))

        with patch("app.api.tasks._get_graph", return_value=fake_graph):
            import asyncio
            from app.api.tasks import task_snapshots
            result = asyncio.run(task_snapshots(task_id="t1"))

        assert result["success"] is True
        assert result["data"]["snapshots"] == []
        assert result["data"]["total"] == 0

    def test_state_without_optional_attrs(self) -> None:
        """state 对象没有 values/metadata/next 属性 → defaults."""
        state = SimpleNamespace(config=None)  # 没有 values/metadata/next/config
        fake_graph = MagicMock()
        fake_graph.get_state_history = MagicMock(return_value=iter([state]))

        with patch("app.api.tasks._get_graph", return_value=fake_graph):
            import asyncio
            from app.api.tasks import task_snapshots
            result = asyncio.run(task_snapshots(task_id="t1"))

        snap = result["data"]["snapshots"][0]
        assert snap["intent"] is None
        assert snap["status"] is None
        assert snap["next"] == []
        assert snap["checkpoint_id"] == ""

    def test_index_increments_per_state(self) -> None:
        """index 字段按枚举顺序递增."""
        states = [
            SimpleNamespace(values={}, metadata={"step": i}, next=(), config=None)
            for i in range(3)
        ]
        fake_graph = MagicMock()
        fake_graph.get_state_history = MagicMock(return_value=iter(states))

        with patch("app.api.tasks._get_graph", return_value=fake_graph):
            import asyncio
            from app.api.tasks import task_snapshots
            result = asyncio.run(task_snapshots(task_id="t1"))

        snaps = result["data"]["snapshots"]
        assert [s["index"] for s in snaps] == [0, 1, 2]
        assert [s["step"] for s in snaps] == [0, 1, 2]


# ─── _get_graph 单例 ──────────────────────────────────────────────────


class TestGetGraphSingleton:
    def test_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """多次调用应返回同一对象."""
        # 重置模块单例
        import app.api.tasks as tasks_mod
        monkeypatch.setattr(tasks_mod, "_graph", None)

        fake_graph = MagicMock()
        with patch("app.api.tasks.create_orchestrator_graph", return_value=fake_graph):
            g1 = _get_graph()
            g2 = _get_graph()

        assert g1 is g2
        assert g1 is fake_graph

    def test_initializes_with_memory_saver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """首次调用时应创建 MemorySaver checkpointer."""
        import app.api.tasks as tasks_mod
        monkeypatch.setattr(tasks_mod, "_graph", None)

        with patch("app.api.tasks.create_orchestrator_graph") as mock_create:
            mock_create.return_value = MagicMock()
            _get_graph()

        # 验证传入了 checkpointer 参数(实际是 MemorySaver 实例)
        call = mock_create.call_args
        assert "checkpointer" in call.kwargs
        from langgraph.checkpoint.memory import MemorySaver
        assert isinstance(call.kwargs["checkpointer"], MemorySaver)


# ─── Auth 覆盖:未注入 token 时应 401 ──────────────────────────────────


class TestAuthRequired:
    def test_list_tasks_requires_user_id(self) -> None:
        """不带任何 token 直接请求 → get_current_user_id 抛 401."""
        app_no_auth = FastAPI()
        app_no_auth.include_router(tasks_router, prefix="/tasks")
        # 不覆盖 get_current_user_id,保留真实依赖
        client = TestClient(app_no_auth, raise_server_exceptions=False)
        resp = client.get("/tasks")
        # 401 from get_current_user_id via HTTPAuthorizationCredentials
        assert resp.status_code in (401, 403)
