"""Dashboard API tests: stats aggregation."""

import uuid
from unittest.mock import patch

import pytest


def _unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@test.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_dashboard_stats_auth_required(client):
    """Dashboard requires authentication."""
    resp = await client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_stats_success(client):
    """Returns KPIs, trend, and recent activities."""
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Dashboard User",
    })
    token = reg.json()["access_token"]

    resp = await client.get("/api/v1/dashboard/stats", headers=_auth_headers(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["kpis"]) == 4
    # KPI keys
    kpi_keys = {k["key"] for k in data["kpis"]}
    assert kpi_keys == {"candidates", "jobs", "interviews", "onboards"}
    # Trend is a list
    assert isinstance(data["trend"], list)
    # Recent activities is a list
    assert isinstance(data["recent_activities"], list)


@pytest.mark.asyncio
async def test_dashboard_stats_structure(client):
    """KPI values are numeric and present."""
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Dashboard User 2",
    })
    token = reg.json()["access_token"]

    resp = await client.get("/api/v1/dashboard/stats", headers=_auth_headers(token))
    data = resp.json()

    for kpi in data["kpis"]:
        assert isinstance(kpi["value"], (int, float))
        assert kpi["value"] >= 0
        assert kpi["label"]
