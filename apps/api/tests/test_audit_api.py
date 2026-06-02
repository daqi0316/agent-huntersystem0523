"""Tests for app/api/audit.py — audit log query endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.audit import router as audit_router


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(audit_router, prefix="/audit")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _make_op_log(
    id: str = "op1",
    agent_name: str = "router",
    action: str = "classify",
    status_value: str = "success",
    error_category: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MagicMock:
    op = MagicMock()
    op.id = id
    op.agent_name = agent_name
    op.action = action
    op.status.value = status_value
    op.error_category = error_category
    op.input_summary = "in"
    op.output_summary = "out"
    op.error_message = None
    op.duration_ms = 100
    op.created_at = created_at or datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    op.updated_at = updated_at or datetime(2025, 6, 15, 10, 0, 5, tzinfo=timezone.utc)
    return op


def _patch_db(app: FastAPI, db_mock):
    """Override get_db dependency to return mock session."""
    from app.core.database import get_db

    async def fake_get_db():
        yield db_mock

    app.dependency_overrides[get_db] = fake_get_db


class TestListAuditLogs:
    def test_no_filters(self, app: FastAPI) -> None:
        """无过滤 → 返回所有日志."""
        client = TestClient(app)
        db = AsyncMock()
        op = _make_op_log()
        count_result = MagicMock()
        count_result.scalar = MagicMock(return_value=1)
        list_result = MagicMock()
        list_result.scalars.return_value.all = MagicMock(return_value=[op])
        db.execute = AsyncMock(side_effect=[count_result, list_result])
        _patch_db(app, db)
        resp = client.get("/audit/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["total"] == 1
        assert len(body["data"]["items"]) == 1
        assert body["data"]["items"][0]["agent_name"] == "router"

    def test_with_agent_filter(self, app: FastAPI) -> None:
        """agent_name 过滤 → 加入 where."""
        client = TestClient(app)
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar = MagicMock(return_value=0)
        list_result = MagicMock()
        list_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(side_effect=[count_result, list_result])
        _patch_db(app, db)
        resp = client.get("/audit/logs?agent_name=router_x")
        assert resp.status_code == 200
        assert db.execute.await_count == 2

    def test_with_error_category_filter(self, app: FastAPI) -> None:
        """error_category 过滤."""
        client = TestClient(app)
        db = AsyncMock()
        op = _make_op_log(status_value="failed", error_category="system")
        count_result = MagicMock()
        count_result.scalar = MagicMock(return_value=1)
        list_result = MagicMock()
        list_result.scalars.return_value.all = MagicMock(return_value=[op])
        db.execute = AsyncMock(side_effect=[count_result, list_result])
        _patch_db(app, db)
        resp = client.get("/audit/logs?error_category=system")
        assert resp.status_code == 200
        item = resp.json()["data"]["items"][0]
        assert item["status"] == "failed"
        assert item["error_category"] == "system"

    def test_with_date_range(self, app: FastAPI) -> None:
        """from_date + to_date 过滤."""
        client = TestClient(app)
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar = MagicMock(return_value=0)
        list_result = MagicMock()
        list_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(side_effect=[count_result, list_result])
        _patch_db(app, db)
        resp = client.get("/audit/logs?from_date=2025-06-01&to_date=2025-06-30")
        assert resp.status_code == 200

    def test_pagination(self, app: FastAPI) -> None:
        """limit/offset 分页."""
        client = TestClient(app)
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar = MagicMock(return_value=100)
        list_result = MagicMock()
        list_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(side_effect=[count_result, list_result])
        _patch_db(app, db)
        resp = client.get("/audit/logs?limit=10&offset=20")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 100

    def test_limit_validation(self, client: TestClient) -> None:
        """limit 超过 500 → 422."""
        resp = client.get("/audit/logs?limit=1000")
        assert resp.status_code == 422


class TestAuditStats:
    def test_stats_success(self, app: FastAPI) -> None:
        """正常返回统计."""
        client = TestClient(app)
        db = AsyncMock()
        total_result = MagicMock()
        total_result.scalar = MagicMock(return_value=42)
        by_agent_result = MagicMock()
        by_agent_result.fetchall = MagicMock(return_value=[("router", 20), ("chat", 22)])
        by_error_result = MagicMock()
        by_error_result.fetchall = MagicMock(return_value=[("system", 5)])
        system_result = MagicMock()
        system_result.scalar = MagicMock(return_value=5)
        db.execute = AsyncMock(side_effect=[total_result, by_agent_result, by_error_result, system_result])
        _patch_db(app, db)
        resp = client.get("/audit/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_operations"] == 42
        assert data["system_errors"] == 5
        assert len(data["by_agent"]) == 2
        assert data["by_agent"][0] == {"agent_name": "router", "count": 20}
        assert len(data["by_error_category"]) == 1
        assert data["by_error_category"][0] == {"category": "system", "count": 5}

    def test_stats_empty(self, app: FastAPI) -> None:
        """无日志 → 全部为 0."""
        client = TestClient(app)
        db = AsyncMock()
        total_result = MagicMock()
        total_result.scalar = MagicMock(return_value=0)
        by_agent_result = MagicMock()
        by_agent_result.fetchall = MagicMock(return_value=[])
        by_error_result = MagicMock()
        by_error_result.fetchall = MagicMock(return_value=[])
        system_result = MagicMock()
        system_result.scalar = MagicMock(return_value=0)
        db.execute = AsyncMock(side_effect=[total_result, by_agent_result, by_error_result, system_result])
        _patch_db(app, db)
        resp = client.get("/audit/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_operations"] == 0
        assert data["system_errors"] == 0
        assert data["by_agent"] == []
        assert data["by_error_category"] == []
