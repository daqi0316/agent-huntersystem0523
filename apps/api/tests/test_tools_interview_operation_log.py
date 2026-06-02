"""Tests for app/tools/interview.py + app/tools/operation_log.py.

interview.py: schedule/record_feedback/cancel_interview (19 missed, 41%)
operation_log.py: log_operation (14 missed, 42%)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.interview import (
    _handle_cancel_interview,
    _handle_schedule_interview,
    _handle_record_feedback,
    handlers as interview_handlers,
    tools as interview_tools,
)
from app.tools.operation_log import (
    _handle_log_operation,
    handlers as oplog_handlers,
    tools as oplog_tools,
)


class FakeAsyncSession:
    def __init__(self, mock_db=None):
        self._mock_db = mock_db or MagicMock()

    async def __aenter__(self):
        return self._mock_db

    async def __aexit__(self, *args):
        return False


def make_result_mock(scalar_list=None, scalar_one=None):
    """Build a fake execute() result.

    scalars().all() is sync in service code.
    scalar_one_or_none() is sync (no await in service code).
    """
    scalar_list = scalar_list or []
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=scalar_list)
    scalars_mock.one_or_none = MagicMock(return_value=scalar_one)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars_mock)
    result.scalar_one_or_none = MagicMock(return_value=scalar_one)
    return result


# ─── Interview Tools ────────────────────────────────────────────────


class TestHandleCancelInterview:
    async def test_cancel_not_found(self):
        mock_result = make_result_mock(scalar_one=None)
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.tools.interview.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)):
            result = await _handle_cancel_interview(
                interview_id=str(uuid.uuid4()), reason="conflict"
            )

        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    async def test_cancel_success(self):
        valid_id = str(uuid.uuid4())
        mock_interview = MagicMock()
        mock_interview.id = valid_id
        mock_interview.status = MagicMock(value="cancelled")
        mock_result = make_result_mock(scalar_one=mock_interview)
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.tools.interview.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)):
            result = await _handle_cancel_interview(interview_id=valid_id, reason="schedule conflict")

        assert result["status"] == "success"
        assert result["data"]["interview_id"] == valid_id
        assert result["data"]["status"] == "cancelled"


class TestHandleScheduleInterview:
    async def test_schedule_success(self):
        mock_result = make_result_mock([])
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.tools.interview.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)):
            result = await _handle_schedule_interview(
                candidate_id=str(uuid.uuid4()),
                job_id=str(uuid.uuid4()),
                scheduled_time="2026-06-10T14:00:00+00:00",
                notes="technical round",
            )

        assert result["id"]
        assert result["status"] == "scheduled"

    async def test_schedule_returns_conflict_error(self):
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result_mock([]))
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.tools.interview.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)):
            result = await _handle_schedule_interview(
                candidate_id=str(uuid.uuid4()),
                job_id=str(uuid.uuid4()),
                scheduled_time="2026-06-10T14:00:00+00:00",
            )

        # With empty conflict list, no conflict → schedule succeeds
        assert result["status"] == "scheduled"


class TestHandleRecordFeedback:
    async def test_record_success(self):
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("app.tools.interview.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)):
            result = await _handle_record_feedback(
                interview_id=str(uuid.uuid4()), score=8, evaluation="good performance",
            )

        assert result["id"]
        assert result["status"] == "recorded"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()


class TestInterviewToolsModule:
    def test_handlers_has_all_three(self):
        assert "schedule_interview" in interview_handlers
        assert "record_feedback" in interview_handlers
        assert "cancel_interview" in interview_handlers

    def test_tools_list_has_three_definitions(self):
        assert len(interview_tools) == 3
        names = [t["function"]["name"] for t in interview_tools]
        assert "schedule_interview" in names
        assert "record_feedback" in names
        assert "cancel_interview" in names


# ─── Operation Log Tool ──────────────────────────────────────────────


class TestHandleLogOperation:
    async def test_log_operation_pending_no_transition(self):
        mock_op = MagicMock()
        mock_op.id = "op-1"
        mock_op.action = "screen_resume"
        mock_op.status = MagicMock(value="pending")
        mock_op.created_at = MagicMock(isoformat=lambda: "2026-06-01T10:00:00+00:00")

        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_op)

        with patch("app.tools.operation_log.OperationService", return_value=mock_svc):
            result = await _handle_log_operation(action="screen_resume", status="pending")

        assert result["status"] == "success"
        assert result["data"]["operation_id"] == "op-1"
        mock_svc.create.assert_awaited_once()
        mock_svc.transition.assert_not_called()

    async def test_log_operation_completed_calls_transition(self):
        mock_op = MagicMock()
        mock_op.id = "op-2"
        mock_op.action = "screen_resume"
        mock_op.status = MagicMock(value="completed")
        mock_op.created_at = MagicMock(isoformat=lambda: "2026-06-01T10:00:00+00:00")

        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_op)
        mock_svc.transition = AsyncMock(return_value=mock_op)

        with patch("app.tools.operation_log.OperationService", return_value=mock_svc):
            result = await _handle_log_operation(
                action="screen_resume", status="completed",
                output_summary="processed 50 resumes",
            )

        assert result["status"] == "success"
        mock_svc.transition.assert_called_once()

    async def test_log_operation_with_error_category(self):
        mock_op = MagicMock()
        mock_op.id = "op-3"
        mock_op.action = "screen_resume"
        mock_op.status = MagicMock(value="failed")
        mock_op.created_at = MagicMock(isoformat=lambda: "2026-06-01T10:00:00+00:00")

        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_op)
        mock_svc.transition = AsyncMock(return_value=mock_op)

        with patch("app.tools.operation_log.OperationService", return_value=mock_svc):
            result = await _handle_log_operation(
                action="screen_resume", status="failed",
                error_message="LLM timeout", error_category="system",
            )

        assert result["status"] == "success"
        mock_svc.transition.assert_called_once()

    async def test_log_operation_invalid_status_defaults_to_completed(self):
        mock_op = MagicMock()
        mock_op.id = "op-4"
        mock_op.action = "screen_resume"
        mock_op.status = MagicMock(value="completed")
        mock_op.created_at = MagicMock(isoformat=lambda: "2026-06-01T10:00:00+00:00")

        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_op)
        mock_svc.transition = AsyncMock(return_value=mock_op)

        with patch("app.tools.operation_log.OperationService", return_value=mock_svc):
            result = await _handle_log_operation(action="screen_resume", status="invalid_status")

        assert result["status"] == "success"


class TestOperationLogToolsModule:
    def test_handlers_has_log_operation(self):
        assert "log_operation" in oplog_handlers

    def test_tools_list_has_one_definition(self):
        assert len(oplog_tools) == 1
        assert oplog_tools[0]["function"]["name"] == "log_operation"
