"""Interview service tests: scheduling, conflict detection, status transitions."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestInterviewServiceUnit:
    """Unit tests for InterviewService with mocked DB session."""

    @pytest.mark.asyncio
    async def test_schedule_interview_success(self):
        """Schedule creates an interview with correct fields."""
        from app.services.interview import InterviewService

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = InterviewService(mock_db)

        result = await service.schedule(
            candidate_id="cand-123",
            job_id="job-456",
            slot={
                "type": "video",
                "scheduled_at": "2025-06-01T10:00:00Z",
                "duration_minutes": 60,
                "location": "Zoom",
                "notes": "Technical interview",
            },
        )

        assert result is not None
        assert "id" in result
        assert result["candidate_id"] == "cand-123"
        assert result["type"] == "video"
        assert result["status"] == "scheduled"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_schedule_with_conflict(self):
        """Schedule detects overlapping time slots."""
        from datetime import datetime, timezone
        from app.services.interview import InterviewService

        existing = MagicMock()
        existing.scheduled_at = datetime.fromisoformat("2025-06-01T09:00:00+00:00")
        existing.duration_minutes = 120
        existing.id = "87654321-8765-4321-8765-432187654321"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing]

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = InterviewService(mock_db)

        result = await service.schedule(
            candidate_id="cand-123",
            job_id="job-456",
            slot={
                "type": "video",
                "scheduled_at": "2025-06-01T10:00:00Z",
                "duration_minutes": 60,
            },
        )

        assert result is not None
        assert "error" in result
        assert result["error"] is True
        assert "占用" in result["message"]

    @pytest.mark.asyncio
    async def test_confirm_interview(self):
        """Confirm transitions status to confirmed."""
        from app.models.interview import InterviewType
        from app.services.interview import InterviewService

        interview_id = "12345678-1234-5678-1234-567812345678"
        mock_interview = MagicMock()
        mock_interview.id = interview_id
        mock_interview.status = "scheduled"
        mock_interview.candidate_id = "cand-123"
        mock_interview.application_id = ""
        mock_interview.type = InterviewType.VIDEO
        mock_interview.scheduled_at = None
        mock_interview.duration_minutes = 60
        mock_interview.location = ""
        mock_interview.notes = ""
        mock_interview.feedback = ""
        mock_interview.created_at = None
        mock_interview.updated_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_interview

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = InterviewService(mock_db)
        result = await service.confirm(interview_id)

        assert result is not None
        assert result["status"] == "confirmed"
        assert mock_interview.status == "confirmed"

    @pytest.mark.asyncio
    async def test_cancel_interview(self):
        """Cancel transitions status to cancelled."""
        from app.models.interview import InterviewType
        from app.services.interview import InterviewService

        interview_id = "87654321-8765-4321-8765-432187654321"
        mock_interview = MagicMock()
        mock_interview.id = interview_id
        mock_interview.status = "scheduled"
        mock_interview.candidate_id = "cand-123"
        mock_interview.application_id = ""
        mock_interview.type = InterviewType.VIDEO
        mock_interview.scheduled_at = None
        mock_interview.duration_minutes = 60
        mock_interview.location = ""
        mock_interview.notes = ""
        mock_interview.feedback = ""
        mock_interview.created_at = None
        mock_interview.updated_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_interview

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = InterviewService(mock_db)
        result = await service.cancel(interview_id)

        assert result is not None
        assert result["status"] == "cancelled"
        assert mock_interview.status == "cancelled"

    @pytest.mark.asyncio
    async def test_complete_interview(self):
        """Complete transitions status to completed."""
        from app.models.interview import InterviewType
        from app.services.interview import InterviewService

        interview_id = "11111111-1111-1111-1111-111111111111"
        mock_interview = MagicMock()
        mock_interview.id = interview_id
        mock_interview.status = "confirmed"
        mock_interview.candidate_id = "cand-123"
        mock_interview.application_id = ""
        mock_interview.type = InterviewType.VIDEO
        mock_interview.scheduled_at = None
        mock_interview.duration_minutes = 60
        mock_interview.location = ""
        mock_interview.notes = ""
        mock_interview.feedback = ""
        mock_interview.created_at = None
        mock_interview.updated_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_interview

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = InterviewService(mock_db)
        result = await service.complete(interview_id, feedback="Good candidate")

        assert result is not None
        assert result["status"] == "completed"
        assert mock_interview.status == "completed"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_interview(self):
        """Cancel on nonexistent interview returns error."""
        from app.services.interview import InterviewService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = InterviewService(mock_db)
        result = await service.cancel("nonexistent-id")

        # Service returns None when interview not found
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all_paginated(self):
        """list_all returns paginated interviews with total."""
        from app.models.interview import InterviewStatus, InterviewType
        from app.services.interview import InterviewService

        mock_interview = MagicMock()
        mock_interview.id = "aaa-bbb-ccc"
        mock_interview.candidate_id = "cand-123"
        mock_interview.application_id = ""
        mock_interview.status = InterviewStatus.SCHEDULED
        mock_interview.type = InterviewType.VIDEO
        mock_interview.duration_minutes = 60
        mock_interview.scheduled_at = None
        mock_interview.location = ""
        mock_interview.notes = ""
        mock_interview.feedback = ""
        mock_interview.created_at = None
        mock_interview.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_interview]

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, mock_result])

        service = InterviewService(mock_db)
        items, total = await service.list_all(skip=0, limit=20)

        assert len(items) >= 1
        assert total == 1
        assert items[0]["id"] == "aaa-bbb-ccc"

    @pytest.mark.asyncio
    async def test_schedule_invalid_type_fallback(self):
        from app.services.interview import InterviewService

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = InterviewService(mock_db)
        result = await service.schedule(
            candidate_id="cand-1",
            job_id="job-1",
            slot={"type": "bad_type", "scheduled_at": "2025-06-01T10:00:00Z"},
        )
        assert result is not None
        assert result["type"] == "video"

    @pytest.mark.asyncio
    async def test_schedule_invalid_datetime_fallback(self):
        from app.services.interview import InterviewService

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = InterviewService(mock_db)
        result = await service.schedule(
            candidate_id="cand-1",
            job_id="job-1",
            slot={"type": "video", "scheduled_at": "not-a-date"},
        )
        assert result is not None
        assert "scheduled_at" in result

    @pytest.mark.asyncio
    async def test_confirm_nonexistent(self):
        from app.services.interview import InterviewService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = InterviewService(mock_db)
        result = await service.confirm("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_complete_nonexistent(self):
        from app.services.interview import InterviewService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = InterviewService(mock_db)
        result = await service.complete("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_candidate(self):
        from app.models.interview import InterviewStatus, InterviewType
        from app.services.interview import InterviewService

        mock_interview = MagicMock()
        mock_interview.id = "iv-1"
        mock_interview.candidate_id = "cand-1"
        mock_interview.application_id = ""
        mock_interview.status = InterviewStatus.SCHEDULED
        mock_interview.type = InterviewType.VIDEO
        mock_interview.duration_minutes = 60
        mock_interview.scheduled_at = None
        mock_interview.location = ""
        mock_interview.notes = ""
        mock_interview.feedback = ""
        mock_interview.created_at = None
        mock_interview.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_interview]

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = InterviewService(mock_db)
        items = await service.list_by_candidate("cand-1")
        assert len(items) == 1
        assert items[0]["id"] == "iv-1"

    @pytest.mark.asyncio
    async def test_list_all_with_valid_status_filter(self):
        from app.models.interview import InterviewStatus, InterviewType
        from app.services.interview import InterviewService

        mock_interview = MagicMock()
        mock_interview.id = "iv-2"
        mock_interview.candidate_id = "cand-2"
        mock_interview.application_id = ""
        mock_interview.status = InterviewStatus.SCHEDULED
        mock_interview.type = InterviewType.VIDEO
        mock_interview.duration_minutes = 60
        mock_interview.scheduled_at = None
        mock_interview.location = ""
        mock_interview.notes = ""
        mock_interview.feedback = ""
        mock_interview.created_at = None
        mock_interview.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_interview]

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, mock_result])

        service = InterviewService(mock_db)
        items, total = await service.list_all(skip=0, limit=20, status="scheduled")
        assert len(items) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_all_with_invalid_status(self):
        from app.services.interview import InterviewService

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, mock_result])

        service = InterviewService(mock_db)
        items, total = await service.list_all(skip=0, limit=20, status="bogus_status")
        assert items == []
        assert total == 0
