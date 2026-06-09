"""Interviews API endpoints test — mock InterviewService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.interview_recording import InterviewRecordingError


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


async def test_list_interviews_with_date_range_filter(client):
    """GET /api/v1/interviews?date_from=&date_to= forwards both to service.list_all."""
    from datetime import datetime
    mock_service = AsyncMock()
    mock_service.list_all.return_value = (
        [
            {"id": "iv-1", "candidate_id": "cand-1", "status": "scheduled",
             "scheduled_at": "2026-06-15T10:00:00Z"},
        ],
        1,
    )

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.get(
            "/api/v1/interviews?date_from=2026-06-01T00:00:00Z&date_to=2026-07-01T00:00:00Z"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    # Verify service.list_all was called with date_from/date_to kwargs
    call_kwargs = mock_service.list_all.call_args.kwargs
    assert "date_from" in call_kwargs
    assert "date_to" in call_kwargs
    assert call_kwargs["date_from"] == datetime.fromisoformat("2026-06-01T00:00:00+00:00")
    assert call_kwargs["date_to"] == datetime.fromisoformat("2026-07-01T00:00:00+00:00")


async def test_list_interviews_no_date_filter_backward_compat(client):
    """GET /api/v1/interviews without date_from/date_to works (向后兼容)."""
    mock_service = AsyncMock()
    mock_service.list_all.return_value = ([], 0)

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.get("/api/v1/interviews")

    assert resp.status_code == 200
    call_kwargs = mock_service.list_all.call_args.kwargs
    assert call_kwargs.get("date_from") is None
    assert call_kwargs.get("date_to") is None


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
    data = resp.json()["data"]
    assert data["id"] == "iv-123"


async def test_get_interview_not_found(client):
    """GET /api/v1/interviews/{id} returns 404 for nonexistent id."""
    mock_service = MagicMock()
    mock_service._get_by_id = AsyncMock(return_value=None)

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.get("/api/v1/interviews/nonexistent-id")

    assert resp.status_code == 404


async def test_upload_interview_recording_success(client):
    mock_recording = MagicMock()
    mock_service = MagicMock()
    mock_service.upload_recording = AsyncMock(return_value=mock_recording)
    mock_service.to_dict.return_value = {"id": "rec-1", "status": "recorded"}

    with patch("app.api.interviews.InterviewRecordingService", return_value=mock_service):
        resp = await client.post(
            "/api/v1/interviews/12345678-1234-5678-1234-567812345678/recordings/upload",
            data={"consent_confirmed": "true", "duration_seconds": "3.5"},
            files={"file": ("recording.webm", b"audio", "audio/webm")},
        )

    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "recorded"
    call_kwargs = mock_service.upload_recording.call_args.kwargs
    assert call_kwargs["consent_confirmed"] is True
    assert call_kwargs["mime_type"] == "audio/webm"


async def test_upload_interview_recording_requires_consent(client):
    mock_service = MagicMock()
    mock_service.upload_recording = AsyncMock(side_effect=InterviewRecordingError(
        "CONSENT_REQUIRED", "录音前必须确认候选人/面试参与方已同意"
    ))

    with patch("app.api.interviews.InterviewRecordingService", return_value=mock_service):
        resp = await client.post(
            "/api/v1/interviews/12345678-1234-5678-1234-567812345678/recordings/upload",
            data={"consent_confirmed": "false"},
            files={"file": ("recording.webm", b"audio", "audio/webm")},
        )

    assert resp.status_code == 400
    assert resp.json()["success"] is False


async def test_transcribe_interview_recording_success(client):
    mock_recording = MagicMock()
    mock_service = MagicMock()
    mock_service.transcribe_recording = AsyncMock(return_value=mock_recording)
    mock_service.to_dict.return_value = {
        "id": "rec-1",
        "status": "transcribed",
        "transcript_text": "mock transcript",
    }

    with patch("app.api.interviews.InterviewRecordingService", return_value=mock_service):
        resp = await client.post(
            "/api/v1/interviews/12345678-1234-5678-1234-567812345678/recordings/rec-1/transcribe"
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "transcribed"


async def test_create_recording_evaluation_requires_transcript(client):
    mock_recording = MagicMock()
    mock_recording.transcript_text = ""
    mock_service = MagicMock()
    mock_service.get_recording = AsyncMock(return_value=mock_recording)

    with patch("app.api.interviews.InterviewRecordingService", return_value=mock_service):
        resp = await client.post(
            "/api/v1/interviews/12345678-1234-5678-1234-567812345678/recordings/rec-1/evaluation",
            json={"candidate_name": "张三"},
        )

    assert resp.status_code == 400
    assert "尚未转写" in resp.json()["error"]


async def test_create_recording_evaluation_success(client):
    mock_recording = MagicMock()
    mock_recording.id = "rec-1"
    mock_recording.transcript_text = "候选人：我负责过支付系统重构。"
    mock_recording_svc = MagicMock()
    mock_recording_svc.get_recording = AsyncMock(return_value=mock_recording)
    mock_eval = MagicMock()
    mock_interview_svc = MagicMock()
    mock_interview_svc.save_evaluation = AsyncMock(return_value=mock_eval)
    mock_interview_svc._eval_to_dict.return_value = {"id": "eval-1", "feedback": "ok"}

    with (
        patch("app.api.interviews.InterviewRecordingService", return_value=mock_recording_svc),
        patch("app.api.interviews.InterviewService", return_value=mock_interview_svc),
    ):
        resp = await client.post(
            "/api/v1/interviews/12345678-1234-5678-1234-567812345678/recordings/rec-1/evaluation",
            json={"candidate_name": "张三", "job_title": "后端工程师", "round": "R1"},
        )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["evaluation"]["id"] == "eval-1"
    assert mock_interview_svc.save_evaluation.call_args.kwargs["dimensions"]["recording_id"] == "rec-1"


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
    data = resp.json()["data"]
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
    assert resp.json()["data"]["status"] == "confirmed"


async def test_cancel_interview(client):
    """PATCH /api/v1/interviews/{id}/cancel transitions to cancelled."""
    mock_service = AsyncMock()
    mock_service.cancel.return_value = {"id": "iv-1", "status": "cancelled"}

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.patch("/api/v1/interviews/iv-1/cancel")

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"


async def test_complete_interview(client):
    """PATCH /api/v1/interviews/{id}/complete transitions to completed + status machine."""
    mock_interview_svc = AsyncMock()
    mock_interview_svc.complete.return_value = {
        "id": "iv-1",
        "candidate_id": "cand-1",
        "status": "completed",
    }

    mock_candidate_svc = MagicMock()
    mock_candidate_svc.complete_interview = AsyncMock(return_value=MagicMock())

    mock_app_svc = AsyncMock()
    mock_app_svc.list.return_value = ([{"id": "app-1"}], 1)

    with (
        patch("app.api.interviews.InterviewService", return_value=mock_interview_svc),
        patch("app.api.interviews.CandidateService", return_value=mock_candidate_svc),
        patch("app.api.interviews.ApplicationService", return_value=mock_app_svc),
    ):
        resp = await client.patch("/api/v1/interviews/iv-1/complete")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "completed"
    mock_candidate_svc.complete_interview.assert_awaited_once_with("cand-1")
    mock_app_svc.list.assert_awaited_once()
    mock_app_svc.update.assert_awaited_once()


async def test_complete_interview_status_machine_coverage(client):
    """Status machine transition is idempotent — candidate already completed."""
    mock_interview_svc = AsyncMock()
    mock_interview_svc.complete.return_value = {
        "id": "iv-1",
        "candidate_id": "cand-1",
        "status": "completed",
    }

    mock_candidate_svc = MagicMock()
    mock_candidate_svc.complete_interview = AsyncMock(
        side_effect=ValueError("already completed")
    )

    mock_app_svc = AsyncMock()
    mock_app_svc.list.return_value = ([], 0)

    with (
        patch("app.api.interviews.InterviewService", return_value=mock_interview_svc),
        patch("app.api.interviews.CandidateService", return_value=mock_candidate_svc),
        patch("app.api.interviews.ApplicationService", return_value=mock_app_svc),
    ):
        resp = await client.patch("/api/v1/interviews/iv-1/complete")

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "completed"
    mock_candidate_svc.complete_interview.assert_awaited_once_with("cand-1")
    mock_app_svc.update.assert_not_awaited()


async def test_complete_interview_not_found(client):
    """PATCH /api/v1/interviews/{id}/complete returns 404 for nonexistent id."""
    mock_service = AsyncMock()
    mock_service.complete.return_value = None

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.patch("/api/v1/interviews/nonexistent/complete")

    assert resp.status_code == 404


async def test_confirm_interview_not_found(client):
    """PATCH /api/v1/interviews/{id}/confirm returns 404 for nonexistent id."""
    mock_service = AsyncMock()
    mock_service.confirm.return_value = None

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.patch("/api/v1/interviews/nonexistent/confirm")

    assert resp.status_code == 404


async def test_from_proposal_success(client):
    """POST /api/v1/interviews/from-proposal creates interview + transitions status."""
    mock_candidate_svc = MagicMock()
    mock_candidate_svc.move_to_interview = AsyncMock(return_value=MagicMock())

    mock_interview_svc = AsyncMock()
    mock_interview_svc.schedule.return_value = {
        "id": "iv-from-prop",
        "candidate_id": "cand-1",
        "job_id": "job-1",
        "type": "video",
        "status": "scheduled",
        "duration_minutes": 60,
        "scheduled_at": "2025-06-01T10:00:00",
    }

    with (
        patch("app.api.interviews.CandidateService", return_value=mock_candidate_svc),
        patch("app.api.interviews.InterviewService", return_value=mock_interview_svc),
    ):
        resp = await client.post(
            "/api/v1/interviews/from-proposal",
            json={
                "candidate_id": "cand-1",
                "job_id": "job-1",
                "scheduled_at": "2025-06-01T10:00:00",
                "type": "video",
                "duration_minutes": 60,
            },
        )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["status"] == "scheduled"
    assert data["candidate_id"] == "cand-1"
    mock_candidate_svc.move_to_interview.assert_awaited_once_with("cand-1")


async def test_from_proposal_candidate_not_found(client):
    """POST /api/v1/interviews/from-proposal returns 404 when candidate missing."""
    mock_candidate_svc = MagicMock()
    mock_candidate_svc.move_to_interview = AsyncMock(return_value=None)

    with patch("app.api.interviews.CandidateService", return_value=mock_candidate_svc):
        resp = await client.post(
            "/api/v1/interviews/from-proposal",
            json={"candidate_id": "nonexistent", "job_id": "job-1"},
        )

    assert resp.status_code == 404


async def test_from_proposal_slot_conflict(client):
    """POST /api/v1/interviews/from-proposal returns 409 on time conflict."""
    mock_candidate_svc = MagicMock()
    mock_candidate_svc.move_to_interview = AsyncMock(return_value=MagicMock())

    mock_interview_svc = AsyncMock()
    mock_interview_svc.schedule.return_value = {
        "error": True,
        "message": "时间槽已被占用",
    }

    with (
        patch("app.api.interviews.CandidateService", return_value=mock_candidate_svc),
        patch("app.api.interviews.InterviewService", return_value=mock_interview_svc),
    ):
        resp = await client.post(
            "/api/v1/interviews/from-proposal",
            json={"candidate_id": "cand-1", "job_id": "job-1"},
        )

    assert resp.status_code == 409


async def test_from_proposal_with_application_lookup(client):
    """Covers UUID-based application lookup + status update (lines 155-166, 186-187)."""
    import uuid
    from unittest.mock import MagicMock

    from app.core.database import get_db
    from app.main import app

    mock_db = MagicMock()
    mock_app = MagicMock()
    mock_app.id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_app

    async def mock_execute(*args, **kwargs):
        return mock_result
    mock_db.execute = mock_execute
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_candidate_svc = MagicMock()
    mock_candidate_svc.move_to_interview = AsyncMock(return_value=MagicMock())

    mock_interview_svc = AsyncMock()
    mock_interview_svc.schedule.return_value = {
        "id": "iv-app",
        "candidate_id": str(uuid.uuid4()),
        "status": "scheduled",
    }

    mock_app_svc = AsyncMock()

    with (
        patch("app.api.interviews.CandidateService", return_value=mock_candidate_svc),
        patch("app.api.interviews.InterviewService", return_value=mock_interview_svc),
        patch("app.api.interviews.ApplicationService", return_value=mock_app_svc),
    ):
        resp = await client.post(
            "/api/v1/interviews/from-proposal",
            json={
                "candidate_id": str(uuid.uuid4()),
                "job_id": str(uuid.uuid4()),
                "scheduled_at": "2025-06-01T10:00:00",
                "type": "video",
                "duration_minutes": 60,
            },
        )

    app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 201
    mock_app_svc.update.assert_awaited_once()


async def test_from_proposal_wrong_status(client):
    """POST /api/v1/interviews/from-proposal returns 400 when candidate not evaluatable."""
    mock_candidate_svc = MagicMock()
    mock_candidate_svc.move_to_interview = AsyncMock(
        side_effect=ValueError("不允许安排面试")
    )

    with patch("app.api.interviews.CandidateService", return_value=mock_candidate_svc):
        resp = await client.post(
            "/api/v1/interviews/from-proposal",
            json={"candidate_id": "cand-active", "job_id": "job-1"},
        )

    assert resp.status_code == 400


async def test_cancel_interview_not_found(client):
    """PATCH /api/v1/interviews/{id}/cancel returns 404 for nonexistent id."""
    mock_service = AsyncMock()
    mock_service.cancel.return_value = None

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.patch("/api/v1/interviews/nonexistent/cancel")

    assert resp.status_code == 404


async def test_create_interview_schedule_returns_none(client):
    """POST /api/v1/interviews returns 404 when service.schedule returns None."""
    mock_service = AsyncMock()
    mock_service.schedule.return_value = None

    with patch("app.api.interviews.InterviewService", return_value=mock_service):
        resp = await client.post(
            "/api/v1/interviews?candidate_id=nonexistent&job_id=job-1"
        )

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "候选人不存在"


async def test_from_proposal_schedule_returns_none(client):
    """POST /api/v1/interviews/from-proposal returns 404
    when interview_svc.schedule returns None after candidate found."""
    mock_candidate_svc = MagicMock()
    mock_candidate_svc.move_to_interview = AsyncMock(return_value=MagicMock())

    mock_interview_svc = AsyncMock()
    mock_interview_svc.schedule.return_value = None

    with (
        patch("app.api.interviews.CandidateService", return_value=mock_candidate_svc),
        patch("app.api.interviews.InterviewService", return_value=mock_interview_svc),
    ):
        resp = await client.post(
            "/api/v1/interviews/from-proposal",
            json={"candidate_id": "cand-1", "job_id": "job-1"},
        )

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "候选人不存在"
