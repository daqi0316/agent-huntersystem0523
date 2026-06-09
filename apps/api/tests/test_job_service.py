from __future__ import annotations

from unittest.mock import AsyncMock, Mock, MagicMock

import pytest

from app.models.job_position import JobPosition
from app.services.job import JobService


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock(return_value=None)
    db.delete = AsyncMock(return_value=None)
    return db


@pytest.fixture
def service(mock_db):
    return JobService(mock_db)


def _make_job(job_id="job-001", title="工程师"):
    j = Mock(spec=JobPosition)
    j.id = job_id
    j.title = title
    j.department = "技术"
    j.job_profile_id = None
    j.profile_version_id = None
    return j


def _configure_db(mock_db, jobs, total=1):
    mr = Mock()
    mr.scalars.return_value.all.return_value = jobs
    mr.scalar.return_value = total
    mock_db.execute.return_value = mr


class TestList:
    async def test_basic(self, service, mock_db):
        _configure_db(mock_db, [_make_job()])
        result, total = await service.list()
        assert len(result) == 1
        assert total == 1

    async def test_with_search(self, service, mock_db):
        _configure_db(mock_db, [_make_job()])
        await service.list(search="工程师")
        assert mock_db.execute.called

    async def test_with_status(self, service, mock_db):
        _configure_db(mock_db, [_make_job()])
        await service.list(status="open")
        assert mock_db.execute.called

    async def test_empty(self, service, mock_db):
        _configure_db(mock_db, [], total=0)
        result, total = await service.list()
        assert result == []
        assert total == 0


class TestGetById:
    async def test_found(self, service, mock_db):
        j = _make_job()
        mr = Mock()
        mr.scalar_one_or_none.return_value = j
        mock_db.execute.return_value = mr
        result = await service.get_by_id("00000000-0000-0000-0000-000000000001")
        assert result is not None

    async def test_invalid_uuid(self, service, mock_db):
        result = await service.get_by_id("not-a-uuid")
        assert result is None


class TestCreate:
    async def test_creates_and_refreshes(self, service, mock_db):
        from app.schemas.job import JobCreate
        data = JobCreate(
            title="新职位",
            department="技术",
            job_profile_id="11111111-1111-1111-1111-111111111107",
            profile_version_id="22222222-2222-2222-2222-222222222222",
        )
        result = await service.create(data)
        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.refresh.called


class TestUpdate:
    async def test_found(self, service, mock_db):
        j = _make_job()
        mr = Mock()
        mr.scalar_one_or_none.return_value = j
        mock_db.execute.return_value = mr
        from app.schemas.job import JobUpdate
        result = await service.update(
            "00000000-0000-0000-0000-000000000001",
            JobUpdate(title="新职位", job_profile_id="11111111-1111-1111-1111-111111111107"),
        )
        assert result is not None
        assert j.job_profile_id == "11111111-1111-1111-1111-111111111107"

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        from app.schemas.job import JobUpdate
        result = await service.update("00000000-0000-0000-0000-000000000001", JobUpdate())
        assert result is None


class TestDelete:
    async def test_success(self, service, mock_db):
        j = _make_job()
        mr = Mock()
        mr.scalar_one_or_none.return_value = j
        mock_db.execute.return_value = mr
        assert await service.delete("00000000-0000-0000-0000-000000000001") is True

    async def test_not_found(self, service, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        assert await service.delete("00000000-0000-0000-0000-000000000001") is False
