"""Dashboard Reports API tests — mock DB aggregations."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app


pytestmark = pytest.mark.asyncio


def _mock_db_with_scalar(return_value: int):
    """Build a mock DB session whose ``execute().scalar()`` returns the given value.

    SQLAlchemy's ``scalar()`` is a synchronous method on the ``Result`` object.
    Must use ``MagicMock`` (not ``AsyncMock``) to avoid returning a coroutine.
    """
    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=return_value)

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_db = MagicMock(spec=AsyncSession)
    mock_db.execute = mock_execute
    return mock_db


async def test_dashboard_reports_success(client):
    """Dashboard reports returns funnel, sources, trend."""
    mock_db = _mock_db_with_scalar(10)
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        resp = await client.get("/api/v1/dashboard/reports")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "funnel" in data["data"]
    assert "sources" in data["data"]
    assert "trend" in data["data"]
    assert len(data["data"]["funnel"]) > 0
    assert data["data"]["sources"][0]["name"] == "主动投递"


async def test_dashboard_reports_empty_db(client):
    """Dashboard reports handles empty database gracefully (sources = [])."""
    mock_db = _mock_db_with_scalar(0)
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        resp = await client.get("/api/v1/dashboard/reports")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"]["sources"], list)
    assert len(data["data"]["sources"]) == 0
    assert len(data["data"]["trend"]) == 7
