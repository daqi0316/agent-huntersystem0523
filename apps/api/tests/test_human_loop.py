"""Human-in-Loop API tests: interview scheduling, approval, emergency stop."""

from unittest.mock import AsyncMock, patch

import pytest


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
    resp = await client.get("/api/v1/human-loop/pending")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_list_history_empty(client):
    """GET /history returns empty list when no history exists."""
    resp = await client.get("/api/v1/human-loop/history")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_emergency_stop(client):
    """Emergency stop clears all pending approvals."""
    resp = await client.post("/api/v1/human-loop/stop", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "Emergency stop triggered"
    assert "cleared_count" in data


# ──────────────────────────────────────────────
# HumanLoopAgent unit tests
# ──────────────────────────────────────────────

from datetime import datetime, timedelta, timezone
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
    assert hl_agent.pending_approvals == {}


@pytest.mark.asyncio
async def test_hl_create_proposal_schedule(hl_llm, hl_agent):
    hl_llm.chat.return_value = (
        '{"recommended_slot": "2025-06-01T10:00", "duration_minutes": 60}'
    )
    p = await hl_agent.create_proposal("schedule_interview", {
        "candidate_name": "Alice", "job_title": "Engineer",
    })
    assert p["action_type"] == "schedule_interview"
    assert p["approval_id"] in hl_agent.pending_approvals
    assert "recommended_slot" in p["proposal"]


@pytest.mark.asyncio
async def test_hl_create_proposal_email(hl_agent):
    p = await hl_agent.create_proposal("send_email", {
        "to": "a@b.com", "subject": "Hello",
    })
    assert p["action_type"] == "send_email"
    assert p["proposal"]["to"] == "a@b.com"


@pytest.mark.asyncio
async def test_hl_create_proposal_unknown_type(hl_agent):
    p = await hl_agent.create_proposal("unknown_action", {"foo": "bar"})
    assert p["action_type"] == "unknown_action"


@pytest.mark.asyncio
async def test_hl_create_proposal_parse_failure(hl_llm, hl_agent):
    hl_llm.chat.return_value = "{{{broken"
    p = await hl_agent.create_proposal("schedule_interview", {"candidate_name": "X"})
    assert "error" in p["proposal"]


@pytest.mark.asyncio
async def test_hl_confirm_approve(hl_agent):
    p = await hl_agent.create_proposal("schedule_interview", {"candidate_name": "A"})
    r = await hl_agent.confirm(p["approval_id"], approved=True)
    assert r["status"] == "approved"
    assert p["approval_id"] not in hl_agent.pending_approvals


@pytest.mark.asyncio
async def test_hl_confirm_reject(hl_agent):
    p = await hl_agent.create_proposal("schedule_interview", {"candidate_name": "A"})
    r = await hl_agent.confirm(p["approval_id"], approved=False)
    assert r["status"] == "rejected"


@pytest.mark.asyncio
async def test_hl_confirm_unknown_id(hl_agent):
    r = await hl_agent.confirm("bogus", approved=True)
    assert "error" in r


@pytest.mark.asyncio
async def test_hl_run_with_confirm(hl_llm, hl_agent):
    hl_llm.chat.return_value = '{"recommended_slot": "2025-06-01T10:00"}'
    proposal = await hl_agent.create_proposal(
        "schedule_interview", {"candidate_name": "A"},
    )
    r = await hl_agent.run({
        "action_type": "schedule_interview",
        "params": {},
        "confirm": True,
        "approval_id": proposal["approval_id"],
        "approved": True,
    })
    assert r["status"] == "approved"


@pytest.mark.asyncio
async def test_hl_run_without_confirm(hl_llm, hl_agent):
    hl_llm.chat.return_value = '{"recommended_slot": "2025-06-01T10:00"}'
    r = await hl_agent.run({
        "action_type": "schedule_interview",
        "params": {"candidate_name": "Alice"},
    })
    assert r["agent"] == "hl"
    assert r["status"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_hl_get_pending_count(hl_agent):
    await hl_agent.create_proposal("schedule_interview", {"candidate_name": "A"})
    await hl_agent.create_proposal("send_email", {"to": "b@c.com"})
    assert hl_agent.get_pending_count() == 2


def test_hl_pending_purge_all(hl_agent):
    hl_agent.pending_approvals["a"] = {
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    hl_agent.pending_approvals["b"] = {
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    hl_agent._pending_purge_all()
    assert len(hl_agent.pending_approvals) == 0


def test_hl_clean_expired(hl_agent):
    hl_agent.pending_approvals["fresh"] = {
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    hl_agent.pending_approvals["stale"] = {
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }
    hl_agent._clean_expired()
    assert "fresh" in hl_agent.pending_approvals
    assert "stale" not in hl_agent.pending_approvals


@pytest.mark.asyncio
async def test_hl_get_pending_proposals(hl_agent):
    await hl_agent.create_proposal("schedule_interview", {"candidate_name": "A"})
    await hl_agent.create_proposal("send_email", {"to": "b@c.com"})
    proposals = hl_agent.get_pending_proposals()
    assert len(proposals) == 2
    assert all(p["status"] == "pending" for p in proposals)


@pytest.mark.asyncio
async def test_hl_get_approval_history(hl_agent):
    p = await hl_agent.create_proposal("schedule_interview", {"candidate_name": "A"})
    await hl_agent.confirm(p["approval_id"], approved=True)
    history = hl_agent.get_approval_history()
    assert len(history) == 1
    assert history[0]["status"] == "approved"
