"""API tests for app/api/human_loop.py — Human-in-Loop endpoints.

Uses `mock.patch` on the global `app.api.human_loop.agent` singleton so no
LLM / real agent logic is exercised.
"""

from unittest.mock import ANY, MagicMock, patch

import pytest


@pytest.fixture
def mock_agent():
    """Patch the global HumanLoopAgent singleton used by the router."""
    with patch("app.api.human_loop.agent") as m:
        # Make the async methods return a coroutine-compatible result
        m.run = AsyncMock(return_value={"status": "awaiting_approval", "approval": {"id": "proposal_1"}})
        m.confirm = AsyncMock(return_value={"status": "approved", "approval_id": "appr_test"})
        m.get_pending_proposals = MagicMock(return_value=[])
        m.get_approval_history = MagicMock(return_value=[])
        m.get_pending_count = MagicMock(return_value=0)
        m._pending_purge_all = MagicMock()
        yield m


from unittest.mock import AsyncMock


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
        assert body["items"] == []

    async def test_with_items(self, client, mock_agent):
        mock_agent.get_pending_proposals = MagicMock(return_value=[{"approval_id": "p1"}])
        resp = await client.get("/api/v1/human-loop/pending")
        body = resp.json()
        assert body["success"] is True
        assert body["items"] == [{"approval_id": "p1"}]
        mock_agent.get_pending_proposals.assert_called_once()


class TestListHistory:
    """GET /api/v1/human-loop/history"""

    async def test_empty(self, client, mock_agent):
        resp = await client.get("/api/v1/human-loop/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["items"] == []

    async def test_with_items(self, client, mock_agent):
        mock_agent.get_approval_history = MagicMock(return_value=[{"approval_id": "h1"}])
        resp = await client.get("/api/v1/human-loop/history?limit=10")
        body = resp.json()
        assert body["success"] is True
        assert body["items"] == [{"approval_id": "h1"}]

    async def test_default_limit(self, client, mock_agent):
        await client.get("/api/v1/human-loop/history")
        mock_agent.get_approval_history.assert_called_once_with(limit=50)

    async def test_custom_limit(self, client, mock_agent):
        await client.get("/api/v1/human-loop/history?limit=5")
        mock_agent.get_approval_history.assert_called_once_with(limit=5)


class TestStopEmergency:
    """POST /api/v1/human-loop/stop"""

    async def test_stop_clears_pending(self, client, mock_agent):
        mock_agent.get_pending_count = MagicMock(return_value=3)
        resp = await client.post("/api/v1/human-loop/stop")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["cleared_count"] == 3
        assert body["message"] == "Emergency stop triggered"
        mock_agent._pending_purge_all.assert_called_once()
