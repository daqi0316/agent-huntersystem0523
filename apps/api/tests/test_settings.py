"""Settings API tests: read, write, delete settings."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db_session():
    """Create and configure a mock DB session."""
    session = AsyncMock()
    return session


@pytest.fixture
def override_get_db(mock_db_session):
    """Override the get_db dependency with a mock session."""
    from app.core.database import get_db
    from app.main import app

    async def _mock_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_setting():
    """Create a mock Setting model instance (SimpleNamespace = serializable)."""
    return SimpleNamespace(
        key="test-key",
        value="test-value",
        user_id=None,
        id="setting-1",
        created_at=datetime(2025, 1, 15, 10, 0, 0),
        updated_at=datetime(2025, 1, 15, 10, 0, 0),
    )


@pytest.mark.asyncio
async def test_list_settings_returns_list(client, override_get_db, mock_db_session):
    """GET returns an array."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    resp = await client.get("/api/v1/settings")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_settings_with_user_id(
    client, override_get_db, mock_db_session, mock_setting
):
    """GET with user_id filter returns filtered results."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_setting]
    mock_db_session.execute.return_value = mock_result

    resp = await client.get("/api/v1/settings?user_id=user-123")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1


@pytest.mark.asyncio
async def test_get_nonexistent_setting_404(client, override_get_db, mock_db_session):
    """GET non-existent key returns 404."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = mock_result

    resp = await client.get("/api/v1/settings/nonexistent-key-test")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_existing_setting_returns_setting(
    client, override_get_db, mock_db_session, mock_setting
):
    """GET existing key returns the setting."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_setting
    mock_db_session.execute.return_value = mock_result

    resp = await client.get("/api/v1/settings/test-key")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["key"] == "test-key"
    assert data["value"] == "test-value"


@pytest.mark.asyncio
async def test_upsert_create_new(
    client, override_get_db, mock_db_session
):
    """PUT creates a new setting when key doesn't exist."""
    now = datetime(2025, 1, 15, 10, 0, 0)

    def _refresh_side_effect(setting):
        """Simulate DB server setting id/dates on refresh."""
        setting.id = "new-setting-id"
        setting.created_at = now
        setting.updated_at = now

    not_found = MagicMock()
    not_found.scalar_one_or_none.return_value = None

    mock_db_session.execute.return_value = not_found
    mock_db_session.refresh = AsyncMock(side_effect=_refresh_side_effect)

    resp = await client.put(
        "/api/v1/settings/new-key", json={"value": "new-value"}
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["key"] == "new-key"
    assert data["value"] == "new-value"


@pytest.mark.asyncio
async def test_upsert_update_existing(
    client, override_get_db, mock_db_session, mock_setting
):
    """PUT updates an existing setting."""
    mock_db_session.refresh = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_setting
    mock_db_session.execute.return_value = mock_result

    resp = await client.put(
        "/api/v1/settings/test-key", json={"value": "updated-value"}
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["key"] == "test-key"
    assert data["value"] == "updated-value"
    mock_db_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_nonexistent_setting_404(client, override_get_db, mock_db_session):
    """DELETE non-existent key returns 404."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = mock_result

    resp = await client.delete("/api/v1/settings/nonexistent-key-test")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_existing_setting_succeeds(
    client, override_get_db, mock_db_session, mock_setting
):
    """DELETE existing key removes setting and returns success."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_setting
    mock_db_session.execute.return_value = mock_result

    resp = await client.delete("/api/v1/settings/test-key")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    mock_db_session.delete.assert_called_once_with(mock_setting)
    mock_db_session.commit.assert_awaited_once()
