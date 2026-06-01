"""Applications API + service tests."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app


@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
def override_get_db(mock_db_session):
    async def _mock_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_create_application_missing_fields_422(client):
    """Create application without required fields returns 422 with unified format."""
    resp = await client.post("/api/v1/applications", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert "error" in body
    assert "details" in body


@pytest.mark.asyncio
async def test_get_nonexistent_application_404(client):
    """Get non-existent application returns 404."""
    resp = await client.get(f"/api/v1/applications/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_applications_default_pagination(client, override_get_db, mock_db_session):
    """List applications returns paginated structure."""
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar.return_value = 0

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_db_session.execute = mock_execute
    resp = await client.get("/api/v1/applications")
    assert resp.status_code == 200
    data = resp.json()
    # ListResponse has items and total
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)


@pytest.mark.asyncio
async def test_update_nonexistent_application_404(client):
    """Update non-existent application returns 404."""
    resp = await client.put("/api/v1/applications/nonexistent-id", json={
        "status": "rejected",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_application_success(client):
    mock_svc = AsyncMock()
    mock_svc.get_by_id.return_value = {"id": "app-1", "status": "screening"}
    with patch("app.api.applications.ApplicationService", return_value=mock_svc):
        resp = await client.get("/api/v1/applications/app-1")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_create_application_success(client):
    mock_svc = AsyncMock()
    mock_svc.create.return_value = {"id": "app-new", "status": "pending"}
    with patch("app.api.applications.ApplicationService", return_value=mock_svc):
        resp = await client.post("/api/v1/applications", json={
            "candidate_id": "cand-1",
            "job_id": "job-1",
        })
    assert resp.status_code == 201
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_update_application_success(client):
    mock_svc = AsyncMock()
    mock_svc.update.return_value = {"id": "app-1", "status": "accepted"}
    with patch("app.api.applications.ApplicationService", return_value=mock_svc):
        resp = await client.put("/api/v1/applications/app-1", json={
            "status": "accepted",
        })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_delete_application_success(client):
    mock_svc = AsyncMock()
    mock_svc.delete.return_value = True
    with patch("app.api.applications.ApplicationService", return_value=mock_svc):
        resp = await client.delete("/api/v1/applications/app-1")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_delete_nonexistent_application_404(client):
    mock_svc = AsyncMock()
    mock_svc.delete.return_value = False
    with patch("app.api.applications.ApplicationService", return_value=mock_svc):
        resp = await client.delete("/api/v1/applications/nonexistent")
    assert resp.status_code == 404


class TestApplicationService:
    """App.service tests for ApplicationService CRUD."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add = AsyncMock()
        db.delete = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def service(self, mock_db):
        from app.services.application import ApplicationService

        return ApplicationService(mock_db)

    @pytest.mark.asyncio
    async def test_list_default_pagination(self, service, mock_db):
        """list returns paginated results with default limit."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        items, total = await service.list()

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_status_filter(self, service, mock_db):
        """list filters by status."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        items, total = await service.list(status="pending")

        assert items == []

    @pytest.mark.asyncio
    async def test_list_candidate_id_filter(self, service, mock_db):
        """list filters by candidate_id."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        items, total = await service.list(candidate_id="cand-123")

        assert items == []

    @pytest.mark.asyncio
    async def test_list_invalid_status_ignored(self, service, mock_db):
        """list silently ignores invalid status value."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        items, total = await service.list(status="invalid_status_xyz")

        assert items == []

    @pytest.mark.asyncio
    async def test_list_with_search(self, service, mock_db):
        """list passes search to the query."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        items, total = await service.list(search="test")

        assert items == []

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_for_invalid_uuid(self, service):
        """get_by_id returns None for invalid UUID format."""
        result = await service.get_by_id("not-a-uuid")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, service, mock_db):
        """get_by_id returns application when found."""
        mock_application = MagicMock()
        mock_application.id = "550e8400-e29b-41d4-a716-446655440000"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_application
        mock_db.execute.return_value = mock_result

        result = await service.get_by_id("550e8400-e29b-41d4-a716-446655440000")
        assert result is mock_application

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, service, mock_db):
        """get_by_id returns None when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_by_id("550e8400-e29b-41d4-a716-446655440000")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_application(self, service, mock_db):
        """create adds application and commits."""
        from app.schemas.application import ApplicationCreate

        data = ApplicationCreate(
            candidate_id="cand-1",
            job_id="job-1",
        )

        mock_application = MagicMock()
        mock_application.id = "new-id"
        mock_db.refresh = AsyncMock()

        with patch(
            "app.services.application.Application", return_value=mock_application
        ):
            result = await service.create(data)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(mock_application)

    @pytest.mark.asyncio
    async def test_update_existing(self, service, mock_db):
        """update modifies and commits when application exists."""
        from app.schemas.application import ApplicationUpdate

        mock_app = MagicMock()
        mock_app.status = "pending"
        mock_app.ai_summary = None
        mock_db.refresh = AsyncMock()

        with patch.object(service, "get_by_id", return_value=mock_app):
            result = await service.update(
                "550e8400-e29b-41d4-a716-446655440000",
                ApplicationUpdate(status="screening"),
            )

        assert result is mock_app
        assert mock_app.status == "screening"
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, service, mock_db):
        """update returns None when application not found."""
        from app.schemas.application import ApplicationUpdate

        with patch.object(service, "get_by_id", return_value=None):
            result = await service.update(
                "550e8400-e29b-41d4-a716-446655440000",
                ApplicationUpdate(status="rejected"),
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_invalid_status_ignored(self, service, mock_db):
        """update silently ignores invalid status enum value."""
        from app.schemas.application import ApplicationUpdate

        mock_app = MagicMock()
        mock_app.status = "pending"
        mock_db.refresh = AsyncMock()

        with patch.object(service, "get_by_id", return_value=mock_app):
            result = await service.update(
                "550e8400-e29b-41d4-a716-446655440000",
                ApplicationUpdate(status="invalid_status_xyz"),
            )

        assert result is mock_app
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_existing(self, service, mock_db):
        """delete removes and commits when application exists."""
        mock_app = MagicMock()

        with patch.object(service, "get_by_id", return_value=mock_app):
            result = await service.delete("550e8400-e29b-41d4-a716-446655440000")

        assert result is True
        mock_db.delete.assert_called_once_with(mock_app)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, service, mock_db):
        """delete returns False when application not found."""
        with patch.object(service, "get_by_id", return_value=None):
            result = await service.delete("550e8400-e29b-41d4-a716-446655440000")

        assert result is False
        mock_db.delete.assert_not_called()
