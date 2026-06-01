"""Tests for operations.py — operation logs API endpoints.

Uses router-level patching to avoid app.main import (no DB connection needed).
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.api.operations import router, WebSocketManager
from app.core.dependencies import get_current_user_id


class TestWebSocketManager:
    def test_connect_accepts_and_stores(self):
        import asyncio
        mgr = WebSocketManager()
        ws = MagicMock()
        ws.accept = AsyncMock()
        asyncio.run(mgr.connect("user-1", ws))
        ws.accept.assert_called_once()
        assert "user-1" in mgr._connections

    def test_disconnect_removes_connection(self):
        mgr = WebSocketManager()
        ws = MagicMock()
        mgr._connections["user-1"] = [ws]
        mgr.disconnect("user-1", ws)
        assert ws not in mgr._connections.get("user-1", [])

    def test_broadcast_sends_to_all(self):
        import asyncio
        mgr = WebSocketManager()
        ws1 = MagicMock()
        ws2 = MagicMock()
        ws1.send_text = AsyncMock()
        ws2.send_text = AsyncMock()
        mgr._connections["user-1"] = [ws1, ws2]
        asyncio.run(mgr.broadcast("test_event", {"key": "value"}))
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    def test_send_to_user_only_targets_user(self):
        import asyncio
        mgr = WebSocketManager()
        ws_target = MagicMock()
        ws_other = MagicMock()
        ws_target.send_text = AsyncMock()
        ws_other.send_text = AsyncMock()
        mgr._connections["user-1"] = [ws_target]
        mgr._connections["user-2"] = [ws_other]
        asyncio.run(mgr.send_to_user("user-1", "event", {"data": 1}))
        ws_target.send_text.assert_called_once()
        ws_other.send_text.assert_not_called()


class TestOperationsAPIRoutes:
    """Test operations API routes using a standalone FastAPI app with mocked dependencies."""

    @pytest.fixture
    def svc_client(self):
        """Create a test client with OperationService patched and no real DB."""
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.include_router(router, prefix="/operations")
        test_app.dependency_overrides[get_current_user_id] = lambda: "test-user-1"

        with TestClient(test_app) as client:
            yield client

    def test_create_operation_completed(self, svc_client):
        mock_op = MagicMock()
        mock_op.id = "op-123"
        mock_op.action = "create_candidate"
        mock_op.status.value = "completed"
        mock_op.created_at.isoformat.return_value = "2026-06-02T10:00:00"

        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_op)
        mock_svc.transition = AsyncMock()

        with patch("app.api.operations.OperationService", return_value=mock_svc):
            resp = svc_client.post(
                "/",
                data={
                    "action": "create_candidate",
                    "agent_name": "hr",
                    "status": "completed",
                    "input_summary": "Create candidate",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["id"] == "op-123"
            mock_svc.transition.assert_called_once()

    def test_create_operation_pending_skips_transition(self, svc_client):
        mock_op = MagicMock()
        mock_op.id = "op-456"
        mock_op.action = "schedule_interview"
        mock_op.status.value = "pending"
        mock_op.created_at.isoformat.return_value = "2026-06-02T10:00:00"

        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_op)
        mock_svc.transition = AsyncMock()

        with patch("app.api.operations.OperationService", return_value=mock_svc):
            resp = svc_client.post(
                "/",
                data={
                    "action": "schedule_interview",
                    "status": "pending",
                },
            )
            assert resp.status_code == 200
            mock_svc.transition.assert_not_called()

    def test_create_operation_with_error_category(self, svc_client):
        mock_op = MagicMock()
        mock_op.id = "op-789"
        mock_op.action = "screening"
        mock_op.status.value = "failed"
        mock_op.created_at.isoformat.return_value = "2026-06-02T10:00:00"

        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_op)
        mock_svc.transition = AsyncMock()

        with patch("app.api.operations.OperationService", return_value=mock_svc):
            resp = svc_client.post(
                "/",
                data={
                    "action": "screening",
                    "status": "failed",
                    "error_category": "rate_limit_exceeded",
                    "error_message": "LLM rate limit",
                },
            )
            assert resp.status_code == 200

    def test_list_operations_empty(self, svc_client):
        mock_svc = AsyncMock()
        mock_svc.list = AsyncMock(return_value=([], 0))

        with patch("app.api.operations.OperationService", return_value=mock_svc):
            resp = svc_client.get("/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["items"] == []
            assert data["data"]["total"] == 0

    def test_list_operations_with_results(self, svc_client):
        mock_op = MagicMock()
        mock_op.id = "op-001"
        mock_op.agent_name = "router_agent"
        mock_op.action = "classify"
        mock_op.status.value = "completed"
        mock_op.input_summary = "Classify"
        mock_op.output_summary = "screening"
        mock_op.error_message = None
        mock_op.duration_ms = 50
        mock_op.created_at.isoformat.return_value = "2026-06-02T10:00:00"
        mock_op.updated_at.isoformat.return_value = "2026-06-02T10:00:01"

        mock_svc = AsyncMock()
        mock_svc.list = AsyncMock(return_value=([mock_op], 1))

        with patch("app.api.operations.OperationService", return_value=mock_svc):
            resp = svc_client.get("/?agent_name=router_agent&status=completed")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["total"] == 1
            assert data["data"]["items"][0]["agent_name"] == "router_agent"
            assert data["data"]["items"][0]["duration_ms"] == 50

    def test_list_operations_pagination(self, svc_client):
        mock_svc = AsyncMock()
        mock_svc.list = AsyncMock(return_value=([], 50))

        with patch("app.api.operations.OperationService", return_value=mock_svc):
            resp = svc_client.get("/?limit=20&offset=40")
            assert resp.status_code == 200
            data = resp.json()
            assert data["data"]["total"] == 50

    def test_get_operation_found(self, svc_client):
        mock_op = MagicMock()
        mock_op.id = "op-found"
        mock_op.agent_name = "router_agent"
        mock_op.action = "classify"
        mock_op.status.value = "completed"
        mock_op.input_summary = "Classify"
        mock_op.output_summary = "screening"
        mock_op.error_message = None
        mock_op.duration_ms = 50
        mock_op.created_at.isoformat.return_value = "2026-06-02T10:00:00"
        mock_op.updated_at.isoformat.return_value = "2026-06-02T10:00:01"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_op

        mock_svc = AsyncMock()
        mock_svc.db.execute = AsyncMock(return_value=mock_result)

        with patch("app.api.operations.OperationService", return_value=mock_svc):
            resp = svc_client.get("/op-found")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["id"] == "op-found"
            assert data["data"]["duration_ms"] == 50

    def test_get_operation_not_found(self, svc_client):
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_svc = AsyncMock()
        mock_svc.db.execute = AsyncMock(return_value=mock_result)

        with patch("app.api.operations.OperationService", return_value=mock_svc):
            resp = svc_client.get("/op-nonexistent")
            assert resp.status_code == 404
            data = resp.json()
            assert data["success"] is False
