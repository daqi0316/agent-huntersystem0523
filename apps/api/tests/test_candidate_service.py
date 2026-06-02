from __future__ import annotations

from unittest.mock import AsyncMock, Mock, MagicMock

import pytest

from app.models.candidate import Candidate, CandidateStatus
from app.services.candidate import CandidateService


@pytest.fixture
def mock_db():
    """MagicMock-based db to avoid AsyncMock._execute_mock_call coroutine leaks.

    CandidateService uses db primarily via ``await db.execute(...)``. Using
    AsyncMock for the whole fixture would create internal ``_execute_mock_call``
    coroutines that Python 3.14's GC flags as unawaited. Instead we use a
    ``MagicMock`` with a real async ``execute`` function.
    """
    db = MagicMock()
    db.add = Mock(return_value=None)
    db.commit = AsyncMock(return_value=None)
    db.refresh = AsyncMock(return_value=None)
    db.delete = AsyncMock(return_value=None)

    async def _execute(*args, **kwargs):
        _execute.called = True
        return db._execute_result
    _execute.called = False
    db.execute = _execute
    db._execute_result = MagicMock()
    return db


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
    mr = MagicMock()
    mr.scalars.return_value.all.return_value = candidates
    mr.scalar.return_value = total
    mock_db._execute_result = mr
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
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        result = await service.get_by_id("00000000-0000-0000-0000-000000000001")
        assert result is not None

    async def test_not_found(self, service, mock_db):
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = None
        mock_db._execute_result = mr
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
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr

        from app.schemas.candidate import CandidateUpdate
        await service.update("00000000-0000-0000-0000-000000000001", CandidateUpdate(name="新名字"))
        assert mock_db.commit.called

    async def test_not_found(self, service, mock_db):
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = None
        mock_db._execute_result = mr
        from app.schemas.candidate import CandidateUpdate
        result = await service.update("00000000-0000-0000-0000-000000000001", CandidateUpdate())
        assert result is None


class TestDelete:
    async def test_success(self, service, mock_db):
        c = _make_candidate()
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        assert await service.delete("00000000-0000-0000-0000-000000000001") is True

    async def test_not_found(self, service, mock_db):
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = None
        mock_db._execute_result = mr
        assert await service.delete("00000000-0000-0000-0000-000000000001") is False


class TestStartScreening:
    async def test_success(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.ACTIVE)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        result = await service.start_screening("00000000-0000-0000-0000-000000000001")
        assert result is not None
        assert result.status == CandidateStatus.EVALUATING

    async def test_wrong_status(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATED)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        with pytest.raises(ValueError):
            await service.start_screening("00000000-0000-0000-0000-000000000001")

    async def test_not_found(self, service, mock_db):
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = None
        mock_db._execute_result = mr
        result = await service.start_screening("00000000-0000-0000-0000-000000000001")
        assert result is None


class TestCompleteScreening:
    async def test_passed(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATING)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        result = await service.complete_screening("00000000-0000-0000-0000-000000000001", True)
        assert result is not None
        assert result.status == CandidateStatus.EVALUATED

    async def test_failed(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATING)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        result = await service.complete_screening("00000000-0000-0000-0000-000000000001", False)
        assert result is not None
        assert result.status == CandidateStatus.FAILED

    async def test_not_found(self, service, mock_db):
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = None
        mock_db._execute_result = mr
        result = await service.complete_screening("00000000-0000-0000-0000-000000000001", True)
        assert result is None


class TestMoveToInterview:
    async def test_success(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATED)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        result = await service.move_to_interview("00000000-0000-0000-0000-000000000001")
        assert result is not None
        assert result.status == CandidateStatus.IN_INTERVIEW
        assert mock_db.commit.called

    async def test_from_in_interview(self, service, mock_db):
        """Already in_interview should still succeed (re-schedule)."""
        c = _make_candidate(status=CandidateStatus.IN_INTERVIEW)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        result = await service.move_to_interview("00000000-0000-0000-0000-000000000001")
        assert result is not None
        assert result.status == CandidateStatus.IN_INTERVIEW

    async def test_wrong_status(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.ACTIVE)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        with pytest.raises(ValueError, match="不允许安排面试"):
            await service.move_to_interview("00000000-0000-0000-0000-000000000001")

    async def test_not_found(self, service, mock_db):
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = None
        mock_db._execute_result = mr
        result = await service.move_to_interview("00000000-0000-0000-0000-000000000001")
        assert result is None


class TestCompleteInterview:
    async def test_success(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.IN_INTERVIEW)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        result = await service.complete_interview("00000000-0000-0000-0000-000000000001")
        assert result is not None
        assert result.status == CandidateStatus.COMPLETED

    async def test_wrong_status(self, service, mock_db):
        c = _make_candidate(status=CandidateStatus.EVALUATED)
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = c
        mock_db._execute_result = mr
        with pytest.raises(ValueError, match="不允许完成面试"):
            await service.complete_interview("00000000-0000-0000-0000-000000000001")

    async def test_not_found(self, service, mock_db):
        mr = MagicMock()
        mr.scalar_one_or_none.return_value = None
        mock_db._execute_result = mr
        result = await service.complete_interview("00000000-0000-0000-0000-000000000001")
        assert result is None
