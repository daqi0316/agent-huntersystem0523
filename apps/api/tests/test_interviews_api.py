"""Interviews API endpoints test — mock InterviewService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = pytest.mark.asyncio


async def test_list_interviews_success(client):
    """GET /api/v1/interviews returns paginated list."""
    mock_service = AsyncMock()
    mock_service.list_all.return_value = (
        [
            {"id": "iv-1", "candidate_id": "cand-1", "status": "scheduled"},
            {"id": "iv-2", "candidate_id": "cand-2", "status": "confirmed"},
        ],
        2,
    )

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.get("/api/v1/interviews")

    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) == 2
    assert data["total"] == 2


async def test_list_interviews_with_status_filter(client):
    """GET /api/v1/interviews filters by status."""
    mock_service = AsyncMock()
    mock_service.list_all.return_value = (
        [
            {"id": "iv-1", "candidate_id": "cand-1", "status": "scheduled"},
        ],
        1,
    )

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.get("/api/v1/interviews?status=scheduled")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "scheduled"


async def test_get_interview_by_id(client):
    """GET /api/v1/interviews/{id} returns interview detail."""
    mock_interview = MagicMock()
    mock_interview.id = "iv-123"
    mock_interview.candidate_id = "cand-1"
    mock_interview.application_id = "app-1"
    mock_interview.status = "scheduled"
    mock_interview.type = "video"
    mock_interview.scheduled_at = None
    mock_interview.duration_minutes = 60
    mock_interview.location = "Zoom"
    mock_interview.notes = ""
    mock_interview.feedback = ""
    mock_interview.created_at = None
    mock_interview.updated_at = None

    mock_service = MagicMock()
    mock_service._get_by_id = AsyncMock(return_value=mock_interview)
    mock_service._to_dict = MagicMock(
        return_value={"id": "iv-123", "status": "scheduled", "type": "video", "candidate_id": "cand-1"}
    )

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.get("/api/v1/interviews/iv-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "iv-123"


async def test_get_interview_not_found(client):
    """GET /api/v1/interviews/{id} returns 404 for nonexistent id."""
    mock_service = MagicMock()
    mock_service._get_by_id = AsyncMock(return_value=None)

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.get("/api/v1/interviews/nonexistent-id")

    assert resp.status_code == 404


async def test_create_interview_success(client):
    """POST /api/v1/interviews creates a new interview."""
    mock_service = AsyncMock()
    mock_service.schedule.return_value = {
        "id": "iv-new",
        "candidate_id": "cand-1",
        "job_id": "job-1",
        "type": "video",
        "status": "scheduled",
        "duration_minutes": 60,
    }

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.post(
            "/api/v1/interviews?candidate_id=cand-1&job_id=job-1&scheduled_at=2025-06-01T10:00:00Z"
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "scheduled"
    assert data["candidate_id"] == "cand-1"


async def test_create_interview_conflict(client):
    """POST /api/v1/interviews returns 409 on time conflict."""
    mock_service = AsyncMock()
    mock_service.schedule.return_value = {
        "error": True,
        "message": "时间冲突:该时间段已被占用",
    }

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.post(
            "/api/v1/interviews?candidate_id=cand-1&job_id=job-1&scheduled_at=2025-06-01T10:00:00Z"
        )

    assert resp.status_code == 409


async def test_confirm_interview(client):
    """PATCH /api/v1/interviews/{id}/confirm transitions to confirmed."""
    mock_service = AsyncMock()
    mock_service.confirm.return_value = {"id": "iv-1", "status": "confirmed"}

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.patch("/api/v1/interviews/iv-1/confirm")

    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


async def test_cancel_interview(client):
    """PATCH /api/v1/interviews/{id}/cancel transitions to cancelled."""
    mock_service = AsyncMock()
    mock_service.cancel.return_value = {"id": "iv-1", "status": "cancelled"}

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.patch("/api/v1/interviews/iv-1/cancel")

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_complete_interview(client):
    """PATCH /api/v1/interviews/{id}/complete transitions to completed."""
    mock_service = AsyncMock()
    mock_service.complete.return_value = {"id": "iv-1", "status": "completed"}

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.patch("/api/v1/interviews/iv-1/complete")

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
