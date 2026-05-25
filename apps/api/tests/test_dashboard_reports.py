"""Dashboard Reports API tests — mock DB aggregations."""

from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.asyncio


async def _report_payload():
    """Simulated dashboard reports response."""
    return {
        "success": True,
        "data": {
            "funnel": [
                {"stage": "待处理", "count": 10, "key": "pending"},
                {"stage": "初筛中", "count": 8, "key": "screening"},
                {"stage": "面试中", "count": 5, "key": "interview"},
                {"stage": "已发 Offer", "count": 3, "key": "offer"},
                {"stage": "已淘汰", "count": 7, "key": "rejected"},
                {"stage": "已撤回", "count": 1, "key": "withdrawn"},
            ],
            "sources": [
                {"name": "主动投递", "count": 35},
                {"name": "内部推荐", "count": 25},
                {"name": "猎头推荐", "count": 15},
                {"name": "社交媒体", "count": 15},
                {"name": "校园招聘", "count": 10},
            ],
            "trend": [
                {"date": "05-18", "count": 3},
                {"date": "05-19", "count": 5},
                {"date": "05-20", "count": 2},
                {"date": "05-21", "count": 7},
                {"date": "05-22", "count": 4},
                {"date": "05-23", "count": 6},
                {"date": "05-24", "count": 1},
            ],
        },
    }


async def test_dashboard_reports_success(client):
    """Dashboard reports returns funnel, sources, trend."""
    mock_db = AsyncMock()
    # db.execute().scalar() chain
    mock_scalar = AsyncMock(return_value=10)
    mock_result = AsyncMock()
    mock_result.scalar = mock_scalar

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_db.execute = mock_execute

    with patch("app.api.dashboard_reports.get_db") as mock_get_db:
        mock_get_db.return_value = mock_db
        resp = await client.get("/api/v1/dashboard/reports")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "funnel" in data["data"]
    assert "sources" in data["data"]
    assert "trend" in data["data"]
    assert len(data["data"]["funnel"]) > 0
    assert data["data"]["sources"][0]["name"] == "主动投递"


async def test_dashboard_reports_empty_db(client):
    """Dashboard reports handles empty database gracefully."""
    mock_db = AsyncMock()
    mock_scalar = AsyncMock(return_value=0)
    mock_result = AsyncMock()
    mock_result.scalar = mock_scalar

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_db.execute = mock_execute

    with patch("app.api.dashboard_reports.get_db") as mock_get_db:
        mock_get_db.return_value = mock_db
        resp = await client.get("/api/v1/dashboard/reports")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # Empty DB should produce empty sources and 0-count funnel
    assert isinstance(data["data"]["sources"], list)
    assert len(data["data"]["trend"]) == 7
