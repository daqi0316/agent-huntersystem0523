"""Human-in-Loop API tests: interview scheduling, approval, emergency stop."""

from unittest.mock import AsyncMock, patch

import pytest
from app.core.dependencies import get_current_user_id
from app.main import app


@pytest.fixture(autouse=True)
def _override_auth():
    async def mock_user_id():
        return "test-user-id"
    app.dependency_overrides[get_current_user_id] = mock_user_id
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


@pytest.mark.asyncio
async def test_schedule_interview(client):
    """Schedule creates a pending approval record."""
    mock_agent = AsyncMock()
    mock_agent.run.return_value = {
        "agent": "interview_scheduler",
        "status": "awaiting_approval",
        "approval": {
            "approval_id": "appr_test001",
            "action_type": "schedule_interview",
            "proposal": {
                "recommended_slot": "2025-06-01T10:00:00",
                "duration_minutes": 60,
                "interview_type": "技术面",
            },
            "status": "pending",
        },
    }

    with patch("app.api.human_loop.agent", mock_agent):
        resp = await client.post("/api/v1/human-loop/schedule", json={
            "action_type": "schedule_interview",
            "params": {
                "candidate_name": "张三",
                "job_title": "Senior Engineer",
                "available_slots": ["2025-06-01T10:00", "2025-06-02T14:00"],
            },
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "awaiting_approval"
    assert data["approval"]["approval_id"] == "appr_test001"


@pytest.mark.asyncio
async def test_approve_action(client):
    """Approve sets status to approved."""
    mock_agent = AsyncMock()
    mock_agent.confirm.return_value = {
        "approval_id": "appr_test001",
        "action_type": "schedule_interview",
        "status": "approved",
        "proposal": {"recommended_slot": "2025-06-01T10:00:00"},
        "feedback": "Looks good",
    }

    with patch("app.api.human_loop.agent", mock_agent):
        resp = await client.post("/api/v1/human-loop/approve", json={
            "action_type": "schedule_interview",
            "approval_id": "appr_test001",
            "approved": True,
            "feedback": "Looks good",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "approved"


@pytest.mark.asyncio
async def test_reject_action(client):
    """Reject sets status to rejected."""
    mock_agent = AsyncMock()
    mock_agent.confirm.return_value = {
        "approval_id": "appr_test002",
        "action_type": "schedule_interview",
        "status": "rejected",
        "proposal": {"recommended_slot": "2025-06-01T10:00:00"},
        "feedback": "Reschedule needed",
    }

    with patch("app.api.human_loop.agent", mock_agent):
        resp = await client.post("/api/v1/human-loop/approve", json={
            "action_type": "schedule_interview",
            "approval_id": "appr_test002",
            "approved": False,
            "feedback": "Reschedule needed",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "rejected"


@pytest.mark.asyncio
async def test_approve_missing_approval_id_400(client):
    """Approve without approval_id returns 400."""
    resp = await client.post("/api/v1/human-loop/approve", json={
        "action_type": "schedule_interview",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_pending_empty(client):
    """GET /pending returns empty list when no proposals exist."""
    mock_agent = AsyncMock()
    mock_agent.get_pending_proposals.return_value = []
    with patch("app.api.human_loop.agent", mock_agent):
        resp = await client.get("/api/v1/human-loop/pending")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_list_history_empty(client):
    """GET /history returns empty list when no history exists."""
    mock_agent = AsyncMock()
    mock_agent.get_approval_history.return_value = []
    mock_agent.get_approval_history = AsyncMock(return_value=[])
    with patch("app.api.human_loop.agent", mock_agent):
        resp = await client.get("/api/v1/human-loop/history")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_emergency_stop(client):
    """Emergency stop clears all pending approvals."""
    mock_agent = AsyncMock()
    mock_agent.get_pending_count.return_value = 0
    with patch("app.api.human_loop.agent", mock_agent):
        resp = await client.post("/api/v1/human-loop/stop", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True




from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.human_loop import HumanLoopAgent


@pytest.fixture
def hl_llm():
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock()
    patcher = patch("app.agents.human_loop.get_llm_client", return_value=mock_llm)
    patcher.start()
    yield mock_llm
    patcher.stop()


@pytest.fixture
def hl_agent():
    return HumanLoopAgent(name="hl")


def test_hl_init(hl_agent):
    assert hl_agent.name == "hl"
    assert hl_agent._llm is None
