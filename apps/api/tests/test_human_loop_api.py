"""API tests for app/api/human_loop.py — Human-in-Loop endpoints.

Uses `mock.patch` on the global `app.api.human_loop.agent` singleton so no
LLM / real agent logic is exercised.
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_agent():
    """Patch the global HumanLoopAgent singleton used by the router."""
    with patch("app.api.human_loop.agent") as m:
        m.run = AsyncMock(return_value={"status": "awaiting_approval", "approval": {"id": "proposal_1"}})
        m.confirm = AsyncMock(return_value={"status": "approved", "approval_id": "appr_test"})
        m.get_pending_proposals = AsyncMock(return_value=[])
        m.get_approval_history = MagicMock(return_value=[])
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
            approval_id="appr_xxx", approved=True, feedback="好的"
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
        mock_agent.get_approval_history = MagicMock(return_value=[{"approval_id": "h1"}])
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
    """POST /api/v1/human-loop/resume"""

    @staticmethod
    def _make_mock_session():
        """Build a minimal mock orchestrator session."""
        session = MagicMock()
        session.session_id = "os_test_session"
        session.task = "筛选候选人"
        session.context = {}
        session.sub_tasks = [{"type": "screening", "description": "筛选张三", "depends_on": []}]
        session.levels = [[0]]
        session.results = [{
            "agent": "screening", "status": "awaiting_approval",
            "summary": "需人工审批",
            "details": {"approval": {"approval_id": "appr_resume_test"}},
        }]
        session.shared_context = {}
        session.paused_at_level = 0
        session.approval_ids = ["appr_resume_test"]
        session.delete = AsyncMock()
        return session

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

    async def test_resume_session_not_found_returns_404(self, client, mock_agent):
        mock_agent.get_approval_status = AsyncMock(return_value={"status": "approved", "found_in": "history"})
        with patch("app.agents.orchestrator_session.OrchestratorSession.find_by_approval_id",
                   AsyncMock(return_value=None)):
            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": "appr_no_session"},
            )
            assert resp.status_code == 404

    async def test_resume_success(self, client, mock_agent):
        mock_agent.get_approval_status = AsyncMock(return_value={"status": "approved", "found_in": "history"})
        mock_session = self._make_mock_session()
        with (
            patch("app.agents.orchestrator_session.OrchestratorSession.find_by_approval_id",
                  AsyncMock(return_value=mock_session)),
            patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockOrch,
        ):
            mock_orch = MagicMock()
            mock_orch.shared_context = {}
            mock_orch.execute_sub_task = AsyncMock(return_value={
                "agent": "screening", "status": "completed",
                "summary": "筛选完成",
                "result": {"summary": "完成"},
                "details": {},
            })
            MockOrch.return_value = mock_orch

            resp = await client.post(
                "/api/v1/human-loop/resume",
                json={"action_type": "schedule_interview", "approval_id": "appr_resume_test"},
            )

            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["status"] == "completed"
            assert body["data"]["summary"] == "编排全部完成"
            assert body["data"]["succeeded"] == 1
            assert body["data"]["failed"] == 0
            mock_session.delete.assert_awaited_once()


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

    async def test_resume_sub_task_exception(self, client, mock_agent):
        mock_agent.get_approval_status = AsyncMock(return_value={"status": "approved", "found_in": "history"})
        mock_session = MagicMock()
        mock_session.session_id = "os_exc_test"
        mock_session.task = "test"
        mock_session.context = {}
        mock_session.sub_tasks = [{"type": "screening", "description": "筛选", "depends_on": []}]
        mock_session.levels = [[0]]
        mock_session.results = [{
            "agent": "screening", "status": "awaiting_approval",
            "summary": "需审批",
            "details": {"approval": {"approval_id": "appr_exc"}},
        }]
        mock_session.shared_context = {}
        mock_session.paused_at_level = 0
        mock_session.approval_ids = ["appr_exc"]
        mock_session.delete = AsyncMock()

        with patch("app.agents.orchestrator_session.OrchestratorSession.find_by_approval_id",
                   AsyncMock(return_value=mock_session)):
            with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockOrch:
                mock_orch = MagicMock()
                mock_orch.shared_context = {}
                mock_orch.execute_sub_task = AsyncMock(side_effect=ValueError("crash!"))
                MockOrch.return_value = mock_orch

                resp = await client.post(
                    "/api/v1/human-loop/resume",
                    json={"action_type": "schedule_interview", "approval_id": "appr_exc"},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["success"] is True
                assert body["data"]["failed"] == 1

    async def test_resume_partial_status(self, client, mock_agent):
        mock_agent.get_approval_status = AsyncMock(return_value={"status": "approved", "found_in": "history"})
        mock_session = MagicMock()
        mock_session.session_id = "os_partial_test"
        mock_session.task = "test"
        mock_session.context = {}
        mock_session.sub_tasks = [{"type": "a", "depends_on": []}, {"type": "b", "depends_on": []}]
        mock_session.levels = [[0, 1]]
        mock_session.results = [
            {"agent": "a", "status": "awaiting_approval", "summary": "待审批", "details": {"approval": {"approval_id": "appr_partial"}}},
            None,
        ]
        mock_session.shared_context = {}
        mock_session.paused_at_level = 0
        mock_session.approval_ids = ["appr_partial"]
        mock_session.delete = AsyncMock()

        with patch("app.agents.orchestrator_session.OrchestratorSession.find_by_approval_id",
                   AsyncMock(return_value=mock_session)):
            with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockOrch:
                mock_orch = MagicMock()
                mock_orch.shared_context = {}
                results = [
                    {"agent": "a", "status": "completed", "summary": "ok", "result": {}, "details": {}},
                    {"agent": "b", "status": "failed", "summary": "failed", "result": {}, "details": {"error": "nope"}},
                ]
                mock_orch.execute_sub_task = AsyncMock(side_effect=results)
                MockOrch.return_value = mock_orch

                resp = await client.post(
                    "/api/v1/human-loop/resume",
                    json={"action_type": "schedule_interview", "approval_id": "appr_partial"},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["success"] is True
                assert body["data"]["status"] == "partial"
                assert body["data"]["succeeded"] == 1
                assert body["data"]["failed"] == 1
