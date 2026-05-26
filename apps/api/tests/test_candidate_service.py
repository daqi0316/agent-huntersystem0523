from __future__ import annotations

from unittest.mock import AsyncMock, Mock, MagicMock

import pytest

from app.models.candidate import Candidate, CandidateStatus
from app.services.candidate import CandidateService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    return CandidateService(mock_db)


def _make_candidate(
    candidate_id="cand-001", name="测试", status=CandidateStatus.ACTIVE
):
    c = Mock(spec=Candidate)
    c.id = candidate_id
    c.name = name
    c.email = "test@example.com"
    c.current_title = "工程师"
    c.status = status
    return c


def _configure_db(mock_db, candidates, total=1):
    mr = Mock()
    mr.scalars.return_value.all.return_value = candidates
    mr.scalar.return_value = total
    mock_db.execute.return_value = mr
    return mr


class TestList:
    async def test_basic(self, service, mock_db):
        _configure_db(mock_db, [_make_candidate()])
        result, total = await service.list()
        assert len(result) == 1
        assert total == 1

    async def test_with_search(self, service, mock_db):
        _configure_db(mock_db, [_make_candidate()])
        await service.list(search="测试")
        assert mock_db.execute.called

    async def test_with_status(self, service, mock_db):
        _configure_db(mock_db, [_make_candidate()])
        await service.list(status="active")
        assert mock_db.execute.called

    async def test_empty(self, service, mock_db):
        _configure_db(mock_db, [], total=0)
        result, total = await service.list()
        assert result == []
        assert total == 0


class TestGetById:
    async def test_found(self, service, mock_db):
        c = _make_candidate()
        mr = AsyncMock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        result = await service.get_by_id("00000000-0000-0000-0000-000000000001")
        assert result is not None

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        result = await service.get_by_id("00000000-0000-0000-0000-000000000001")
        assert result is None

    async def test_invalid_uuid(self, service, mock_db):
        result = await service.get_by_id("not-a-uuid")
        assert result is None


class TestCreate:
    async def test_creates_and_refreshes(self, service, mock_db):
        from app.schemas.candidate import CandidateCreate
        data = CandidateCreate(name="新候选人", email="new@test.com")
        result = await service.create(data)
        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.refresh.called


class TestUpdate:
    async def test_found(self, service, mock_db):
        c = _make_candidate()
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr

        from app.schemas.candidate import CandidateUpdate
        await service.update("00000000-0000-0000-0000-000000000001", CandidateUpdate(name="新名字"))
        assert mock_db.commit.called

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        from app.schemas.candidate import CandidateUpdate
        result = await service.update("00000000-0000-0000-0000-000000000001", CandidateUpdate())
        assert result is None


class TestDelete:
    async def test_success(self, service, mock_db):
        c = _make_candidate()
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        assert await service.delete("00000000-0000-0000-0000-000000000001") is True

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        assert await service.delete("00000000-0000-0000-0000-000000000001") is False


class TestStartScreening:
    async def test_success(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.ACTIVE)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        result = await service.start_screening("00000000-0000-0000-0000-000000000001")
        assert result is not None
        assert result.status == CandidateStatus.EVALUATING

    async def test_wrong_status(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATED)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        with pytest.raises(ValueError):
            await service.start_screening("00000000-0000-0000-0000-000000000001")

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        result = await service.start_screening("00000000-0000-0000-0000-000000000001")
        assert result is None


class TestCompleteScreening:
    async def test_passed(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATING)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        result = await service.complete_screening("00000000-0000-0000-0000-000000000001", True)
        assert result is not None
        assert result.status == CandidateStatus.EVALUATED

    async def test_failed(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATING)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        result = await service.complete_screening("00000000-0000-0000-0000-000000000001", False)
        assert result is not None
        assert result.status == CandidateStatus.FAILED

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        result = await service.complete_screening("00000000-0000-0000-0000-000000000001", True)
        assert result is None


class TestMoveToInterview:
    async def test_success(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATED)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        result = await service.move_to_interview("00000000-0000-0000-0000-000000000001")
        assert result is not None
        assert result.status == CandidateStatus.IN_INTERVIEW
        assert mock_db.commit.called

    async def test_from_in_interview(self, service, mock_db):
        """Already in_interview should still succeed (re-schedule)."""
        c = _make_candidate(status=CandidateStatus.IN_INTERVIEW)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        result = await service.move_to_interview("00000000-0000-0000-0000-000000000001")
        assert result is not None
        assert result.status == CandidateStatus.IN_INTERVIEW

    async def test_wrong_status(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.ACTIVE)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        with pytest.raises(ValueError, match="不允许安排面试"):
            await service.move_to_interview("00000000-0000-0000-0000-000000000001")

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        result = await service.move_to_interview("00000000-0000-0000-0000-000000000001")
        assert result is None


class TestCompleteInterview:
    async def test_success(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.IN_INTERVIEW)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        result = await service.complete_interview("00000000-0000-0000-0000-000000000001")
        assert result is not None
        assert result.status == CandidateStatus.COMPLETED

    async def test_wrong_status(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATED)
        mr = Mock()
        mr.scalar_one_or_none.return_value = c
        mock_db.execute.return_value = mr
        with pytest.raises(ValueError, match="不允许完成面试"):
            await service.complete_interview("00000000-0000-0000-0000-000000000001")

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        result = await service.complete_interview("00000000-0000-0000-0000-000000000001")
        assert result is None
