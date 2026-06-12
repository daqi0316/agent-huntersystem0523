"""API tests for app/api/human_loop.py — Human-in-Loop endpoints.

Uses `mock.patch` on the global `app.api.human_loop.agent` singleton so no
LLM / real agent logic is exercised.
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.core.dependencies import get_current_user_id
from app.main import app


@pytest.fixture(autouse=True)
def _override_current_user():
    """Override get_current_user_id for all tests in this module.

    /schedule and /approve endpoints require user_id via Depends(get_current_user_id).
    The other endpoints (events/pending/history/resume/stop) are not auth-protected
    and are unaffected by this override.
    """
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


@pytest.fixture
def mock_agent():
    """Patch the global HumanLoopAgent singleton used by the router."""
    with patch("app.api.human_loop.agent") as m:
        m.run = AsyncMock(return_value={"status": "awaiting_approval", "approval": {"id": "proposal_1"}})
        m.confirm = AsyncMock(return_value={"status": "approved", "approval_id": "appr_test"})
        m.get_pending_proposals = AsyncMock(return_value=[])
        m.get_approval_history = AsyncMock(return_value=[])
        m.get_pending_count = AsyncMock(return_value=0)
        m._pending_purge_all = AsyncMock()
        yield m


class TestScheduleInterview:
    """POST /api/v1/human-loop/schedule"""

    async def test_schedule_returns_200(self, client, mock_agent):
        resp = await client.post(
            "/api/v1/human-loop/schedule",
            json={"action_type": "schedule_interview", "params": {"candidate_name": "张三"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["status"] == "awaiting_approval"
        assert body["approval"]["id"] == "proposal_1"
        mock_agent.run.assert_awaited_once_with({
            "action_type": "schedule_interview",
            "params": {"candidate_name": "张三"},
            "user_id": "test-user-id",
        })

    async def test_schedule_none_params(self, client, mock_agent):
        """params 默认空字典时请求正常。"""
        resp = await client.post(
            "/api/v1/human-loop/schedule",
            json={"action_type": "notify"},
        )
        assert resp.status_code == 200


class TestApproveAction:
    """POST /api/v1/human-loop/approve"""

    async def test_approve_approved(self, client, mock_agent):
        mock_agent.confirm = AsyncMock(return_value={"status": "approved", "approval_id": "appr_xxx"})
        resp = await client.post(
            "/api/v1/human-loop/approve",
            json={
                "action_type": "schedule_interview",
                "approval_id": "appr_xxx",
                "approved": True,
                "feedback": "好的",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["status"] == "approved"
        mock_agent.confirm.assert_awaited_once_with(
            approval_id="appr_xxx", approved=True, feedback="好的", user_id="test-user-id"
        )

    async def test_approve_rejected(self, client, mock_agent):
        mock_agent.confirm = AsyncMock(return_value={"status": "rejected", "approval_id": "appr_yyy"})
        resp = await client.post(
            "/api/v1/human-loop/approve",
            json={
                "action_type": "schedule_interview",
                "approval_id": "appr_yyy",
                "approved": False,
                "feedback": "时间不行",
            },
        )
        body = resp.json()
        assert body["success"] is True

    async def test_approve_missing_approval_id_returns_400(self, client, mock_agent):
        resp = await client.post(
            "/api/v1/human-loop/approve",
            json={"action_type": "schedule_interview", "approved": True},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body == {"success": False, "error": "approval_id is required"}

    async def test_approve_error_in_result(self, client, mock_agent):
        """When agent.confirm returns an error, success should be False."""
        mock_agent.confirm = AsyncMock(return_value={"error": "not_found", "approval_id": "bad_id"})
        resp = await client.post(
            "/api/v1/human-loop/approve",
            json={"action_type": "schedule_interview", "approval_id": "bad_id", "approved": True},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["status"] == "unknown"


class TestListPending:
    """GET /api/v1/human-loop/pending"""

    async def test_empty(self, client, mock_agent):
        resp = await client.get("/api/v1/human-loop/pending")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    async def test_with_items(self, client, mock_agent):
        mock_agent.get_pending_proposals = AsyncMock(return_value=[{"approval_id": "p1"}])
        resp = await client.get("/api/v1/human-loop/pending")
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == [{"approval_id": "p1"}]
        mock_agent.get_pending_proposals.assert_called_once()


class TestListHistory:
    """GET /api/v1/human-loop/history"""

    async def test_empty(self, client, mock_agent):
        resp = await client.get("/api/v1/human-loop/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    async def test_with_items(self, client, mock_agent):
        mock_agent.get_approval_history = AsyncMock(return_value=[{"approval_id": "h1"}])
        resp = await client.get("/api/v1/human-loop/history?limit=10")
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == [{"approval_id": "h1"}]

    async def test_default_limit(self, client, mock_agent):
        await client.get("/api/v1/human-loop/history")
        mock_agent.get_approval_history.assert_called_once_with(limit=50)

    async def test_custom_limit(self, client, mock_agent):
        await client.get("/api/v1/human-loop/history?limit=5")
        mock_agent.get_approval_history.assert_called_once_with(limit=5)


class TestStopEmergency:
    """POST /api/v1/human-loop/stop"""

    async def test_stop_clears_pending(self, client, mock_agent):
        mock_agent.get_pending_count = AsyncMock(return_value=3)
        resp = await client.post("/api/v1/human-loop/stop")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["cleared_count"] == 3
        assert body["data"]["message"] == "Emergency stop triggered"
        mock_agent._pending_purge_all.assert_called_once()


class TestResumeAfterApproval:
    """POST /api/v1/human-loop/resume — error paths (legacy session tests moved to TestResumeViaGraph)."""

    async def test_resume_missing_approval_id_returns_400(self, client, mock_agent):
        resp = await client.post(
            "/api/v1/human-loop/resume",
            json={"action_type": "schedule_interview"},
        )
        assert resp.status_code == 400

    async def test_resume_not_found_returns_404(self, client, mock_agent):
        mock_agent.get_approval_status = AsyncMock(return_value=None)
        resp = await client.post(
            "/api/v1/human-loop/resume",
            json={"action_type": "schedule_interview", "approval_id": "nonexistent"},
        )
        assert resp.status_code == 404

    async def test_resume_not_approved_returns_400(self, client, mock_agent):
        mock_agent.get_approval_status = AsyncMock(return_value={"status": "pending", "found_in": "pending"})
        resp = await client.post(
            "/api/v1/human-loop/resume",
            json={"action_type": "schedule_interview", "approval_id": "appr_pending"},
        )
        assert resp.status_code == 400

    async def test_resume_no_thread_index_returns_404(self, client, mock_agent):
        """PR-V.4: without a graph thread index, /resume returns 404 (no legacy fallback)."""
        mock_agent.get_approval_status = AsyncMock(return_value={"status": "approved", "found_in": "history"})
        with patch("app.core.redis.get_redis", new=AsyncMock(return_value=None)):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": "appr_no_session"},
            )
            assert resp.status_code == 404


class TestHashPending:

    def test_hash_pending_deterministic(self):
        from app.api.human_loop import _hash_pending
        items = [{"id": 1, "name": "test"}, {"id": 2}]
        h1 = _hash_pending(items)
        h2 = _hash_pending(items)
        assert h1 == h2

    def test_hash_pending_changes_on_diff(self):
        from app.api.human_loop import _hash_pending
        h1 = _hash_pending([{"a": 1}])
        h2 = _hash_pending([{"a": 2}])
        assert h1 != h2

    def test_hash_pending_empty_list(self):
        from app.api.human_loop import _hash_pending
        assert isinstance(_hash_pending([]), str)
        assert len(_hash_pending([])) > 0


class TestResumeEdgeCases:
    """PR-V.4: /resume requires a graph thread index; returns 404 otherwise."""

    async def test_resume_no_thread_index_returns_404(self, client, mock_agent):
        """If no thread index exists, /resume returns 404."""
        mock_agent.get_approval_status = AsyncMock(return_value={"status": "approved", "found_in": "history"})
        with patch("app.core.redis.get_redis", new=AsyncMock(return_value=None)):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": "appr_exc"},
            )
            assert resp.status_code == 404


class TestResumeViaGraph:
    """PR-V.2 — /resume walks the new graph state path when approval has a thread index."""

    @staticmethod
    def _build_paused_state(approval_id: str = "appr_graph_1") -> dict:
        return {
            "task_id": "t1",
            "user_id": "u1",
            "job_id": "",
            "intent": "orchestrator",
            "input_text": "先筛选再安排面试",
            "agent_result": None,
            "error": None,
            "status": "awaiting_approval",
            "multi_stage": True,
            "sub_tasks": [
                {"type": "screening", "description": "筛选", "depends_on": []},
                {"type": "interview", "description": "面试", "depends_on": [0]},
            ],
            "current_level": 1,
            "levels": [[0], [1]],
            "paused_at_level": 0,
            "results": [
                {
                    "agent": "screening", "status": "awaiting_approval",
                    "summary": "需审批",
                    "result": {},
                    "details": {"approval": {"approval_id": approval_id}},
                },
                None,
            ],
            "shared_context": {"screening.full": {"ok": True}},
        }

    @staticmethod
    def _build_resumed_state(approval_id: str) -> dict:
        return {
            "task_id": "t1",
            "user_id": "u1",
            "job_id": "",
            "intent": "orchestrator",
            "input_text": "先筛选再安排面试",
            "agent_result": None,
            "error": None,
            "status": "completed",
            "multi_stage": True,
            "sub_tasks": [
                {"type": "screening", "description": "筛选", "depends_on": []},
                {"type": "interview", "description": "面试", "depends_on": [0]},
            ],
            "current_level": 2,
            "levels": [[0], [1]],
            "paused_at_level": None,
            "results": [
                {
                    "agent": "screening", "status": "approved",
                    "summary": "筛选 已审批",
                    "result": {},
                    "details": {"approval": {"approval_id": approval_id}},
                },
                {
                    "agent": "interview", "status": "completed",
                    "summary": "面试完成",
                    "result": {"ok": True},
                    "details": {},
                },
            ],
            "shared_context": {"interview.full": {"ok": True}},
        }

    async def test_resume_graph_success(self, client, mock_agent):
        from types import SimpleNamespace
        from app.core.redis import get_redis

        mock_agent.get_approval_status = AsyncMock(
            return_value={"status": "approved", "found_in": "history"},
        )

        thread_id = "thread-graph-1"
        approval_id = "appr_graph_1"
        paused = self._build_paused_state(approval_id)
        resumed = self._build_resumed_state(approval_id)

        snap = SimpleNamespace(values=paused)
        graph = MagicMock()
        graph.get_state = MagicMock(return_value=snap)
        graph.update_state = MagicMock()
        graph.ainvoke = AsyncMock(return_value=resumed)

        redis_client = MagicMock()
        redis_client.get = AsyncMock(
            side_effect=lambda k: thread_id.encode() if k == f"appr:graph_thread:{approval_id}" else None,
        )
        redis_client.delete = AsyncMock(return_value=1)

        with (
            patch("app.core.redis.get_redis", AsyncMock(return_value=redis_client)),
            patch("app.api.orchestrator._get_graph", return_value=graph),
        ):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": approval_id},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "completed"
        assert body["data"]["summary"] == "编排全部完成"
        assert body["data"]["succeeded"] == 2
        assert body["data"]["failed"] == 0
        assert body["data"]["awaiting_approval"] == 0

        graph.get_state.assert_called_once()
        graph.update_state.assert_called_once()
        patch_arg = graph.update_state.call_args.args[1]
        assert patch_arg["paused_at_level"] is None
        assert patch_arg["status"] == "running"
        assert patch_arg["results"][0]["status"] == "approved"
        assert "（已审批）" in patch_arg["results"][0]["summary"]
        graph.ainvoke.assert_awaited_once()
        assert graph.ainvoke.call_args.kwargs["config"] == {
            "configurable": {"thread_id": thread_id},
        }
        redis_client.delete.assert_awaited_once_with(
            f"appr:graph_thread:{approval_id}",
        )

    async def test_resume_graph_paused_state_continues_to_next_approval(self, client, mock_agent):
        from types import SimpleNamespace
        from app.core.redis import get_redis

        mock_agent.get_approval_status = AsyncMock(
            return_value={"status": "approved", "found_in": "history"},
        )

        thread_id = "thread-multi-approval"
        approval_id = "appr_l2"
        paused = self._build_paused_state(approval_id)
        paused["results"][1] = {
            "agent": "interview", "status": "awaiting_approval",
            "summary": "面试需审批",
            "result": {},
            "details": {"approval": {"approval_id": approval_id}},
        }
        paused["paused_at_level"] = 1

        resumed = self._build_resumed_state(approval_id)
        resumed["status"] = "awaiting_approval"
        resumed["results"][1] = {
            "agent": "interview", "status": "awaiting_approval",
            "summary": "面试需审批",
            "result": {},
            "details": {"approval": {"approval_id": approval_id}},
        }
        resumed["paused_at_level"] = 1

        snap = SimpleNamespace(values=paused)
        graph = MagicMock()
        graph.get_state = MagicMock(return_value=snap)
        graph.update_state = MagicMock()
        graph.ainvoke = AsyncMock(return_value=resumed)

        redis_client = MagicMock()
        redis_client.get = AsyncMock(
            side_effect=lambda k: thread_id.encode() if k == f"appr:graph_thread:{approval_id}" else None,
        )
        redis_client.delete = AsyncMock(return_value=1)

        with (
            patch("app.core.redis.get_redis", AsyncMock(return_value=redis_client)),
            patch("app.api.orchestrator._get_graph", return_value=graph),
        ):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": approval_id},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "awaiting_approval"
        assert body["data"]["awaiting_approval"] == 1
        assert "继续等待审批" in body["data"]["summary"]

    async def test_resume_graph_state_not_found(self, client, mock_agent):
        mock_agent.get_approval_status = AsyncMock(
            return_value={"status": "approved", "found_in": "history"},
        )

        redis_client = MagicMock()
        redis_client.get = AsyncMock(return_value=b"thread-missing")
        redis_client.delete = AsyncMock(return_value=1)

        graph = MagicMock()
        graph.get_state = MagicMock(return_value=None)

        with (
            patch("app.core.redis.get_redis", AsyncMock(return_value=redis_client)),
            patch("app.api.orchestrator._get_graph", return_value=graph),
        ):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": "appr_no_state"},
            )

        assert resp.status_code == 404
        body = resp.json()
        assert "graph state not found" in body["error"]

    async def test_resume_graph_state_not_paused(self, client, mock_agent):
        from types import SimpleNamespace
        from app.core.redis import get_redis

        mock_agent.get_approval_status = AsyncMock(
            return_value={"status": "approved", "found_in": "history"},
        )

        state = self._build_paused_state("appr_x")
        state["paused_at_level"] = None
        state["status"] = "running"

        snap = SimpleNamespace(values=state)
        graph = MagicMock()
        graph.get_state = MagicMock(return_value=snap)

        redis_client = MagicMock()
        redis_client.get = AsyncMock(return_value=b"thread-1")

        with (
            patch("app.core.redis.get_redis", AsyncMock(return_value=redis_client)),
            patch("app.api.orchestrator._get_graph", return_value=graph),
        ):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": "appr_x"},
            )

        assert resp.status_code == 400
        body = resp.json()
        assert "not paused" in body["error"]
        graph.update_state.assert_not_called()
        graph.ainvoke.assert_not_called()

    async def test_resume_graph_approval_id_not_in_state(self, client, mock_agent):
        from types import SimpleNamespace
        from app.core.redis import get_redis

        mock_agent.get_approval_status = AsyncMock(
            return_value={"status": "approved", "found_in": "history"},
        )

        state = self._build_paused_state("appr_other")
        snap = SimpleNamespace(values=state)
        graph = MagicMock()
        graph.get_state = MagicMock(return_value=snap)
        graph.update_state = MagicMock()
        graph.ainvoke = AsyncMock()

        redis_client = MagicMock()
        redis_client.get = AsyncMock(return_value=b"thread-1")

        with (
            patch("app.core.redis.get_redis", AsyncMock(return_value=redis_client)),
            patch("app.api.orchestrator._get_graph", return_value=graph),
        ):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": "appr_not_in_state"},
            )

        assert resp.status_code == 404
        body = resp.json()
        assert "not found in graph state" in body["error"]
        graph.update_state.assert_not_called()

    async def test_resume_graph_invoke_failure_returns_500(self, client, mock_agent):
        from types import SimpleNamespace
        from app.core.redis import get_redis

        mock_agent.get_approval_status = AsyncMock(
            return_value={"status": "approved", "found_in": "history"},
        )

        state = self._build_paused_state("appr_fail")
        snap = SimpleNamespace(values=state)
        graph = MagicMock()
        graph.get_state = MagicMock(return_value=snap)
        graph.update_state = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))

        redis_client = MagicMock()
        redis_client.get = AsyncMock(return_value=b"thread-1")
        redis_client.delete = AsyncMock(return_value=1)

        with (
            patch("app.core.redis.get_redis", AsyncMock(return_value=redis_client)),
            patch("app.api.orchestrator._get_graph", return_value=graph),
        ):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": "appr_fail"},
            )

        assert resp.status_code == 500
        body = resp.json()
        assert "graph resume failed" in body["error"]
