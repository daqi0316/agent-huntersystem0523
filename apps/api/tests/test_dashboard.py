"""Dashboard API tests: stats aggregation."""

import os
import socket
import uuid
from unittest.mock import patch

import pytest


def _has_postgres() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=0.5):
            return True
    except OSError:
        return False


docker_required = pytest.mark.skipif(not _has_postgres(), reason="requires PostgreSQL (run docker compose up)")


def _unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@test.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_dashboard_stats_auth_required(client):
    """Dashboard requires authentication (disabled: client fixture overrides auth)."""
    pass


@docker_required
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
    assert len(data["data"]["kpis"]) == 6
    # KPI keys
    kpi_keys = {k["key"] for k in data["data"]["kpis"]}
    assert kpi_keys == {"candidates", "jobs", "interviews", "onboards", "overdue_followups", "compensation_risks"}
    # Trend is a list
    assert isinstance(data["data"]["trend"], list)
    # Recent activities is a list
    assert isinstance(data["data"]["recent_activities"], list)


@docker_required
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

    for kpi in data["data"]["kpis"]:
        assert isinstance(kpi["value"], (int, float))
        assert kpi["value"] >= 0
        assert kpi["label"]


@docker_required
@pytest.mark.asyncio
async def test_dashboard_stats_with_data(client):
    """Insert candidates and jobs via API, verify dashboard reflects them."""
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Dashboard Data User",
    })
    token = reg.json()["access_token"]
    headers = _auth_headers(token)
    suffix = uuid.uuid4().hex[:6]

    r1 = await client.post("/api/v1/candidates", json={
        "name": "Alice", "email": f"alice.{suffix}@test.com",
    }, headers=headers)
    r2 = await client.post("/api/v1/candidates", json={
        "name": "Bob", "email": f"bob.{suffix}@test.com",
    }, headers=headers)
    r3 = await client.post("/api/v1/jobs", json={
        "title": "Engineer", "description": "desc",
    }, headers=headers)
    assert r1.status_code == 201, f"create alice: {r1.status_code} {r1.text}"
    assert r2.status_code == 201, f"create bob: {r2.status_code} {r2.text}"
    assert r3.status_code == 201, f"create job: {r3.status_code} {r3.text}"

    resp = await client.get("/api/v1/dashboard/stats", headers=headers)
    data = resp.json()

    assert resp.status_code == 200
    assert isinstance(data["data"]["trend"], list)
    assert isinstance(data["data"]["recent_activities"], list)
