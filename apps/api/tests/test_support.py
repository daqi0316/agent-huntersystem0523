"""P6-6: 工单 — 5 endpoint 测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.support import router
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def override_db(app, mock_db):
    from app.core.database import get_db
    from app.core.org_context import OrgContext, org_scoped_db

    async def _mock_get_db():
        yield mock_db

    async def _mock_org_scoped_db():
        org_ctx = OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr")
        yield org_ctx, mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[org_scoped_db] = _mock_org_scoped_db
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(org_scoped_db, None)


def _mock_ticket(ticket_id: str = "t-1", status: str = "open", priority: str = "normal"):
    t = MagicMock()
    t.id = ticket_id
    t.subject = "测试工单"
    t.status = MagicMock()
    t.status.value = status
    t.priority = MagicMock()
    t.priority.value = priority
    t.category = "general"
    t.assigned_to = None
    t.org_id = "test-org-id"
    t.user_id = "test-user-id"
    from datetime import datetime
    now = datetime(2026, 6, 6, 14, 0, 0)
    t.created_at = now
    t.updated_at = now
    t.resolved_at = None
    t.closed_at = None
    return t


def _mock_message(message_id: str = "m-1", body: str = "测试消息"):
    m = MagicMock()
    m.id = message_id
    m.ticket_id = "t-1"
    m.sender_type = MagicMock()
    m.sender_type.value = "customer"
    m.sender_id = "test-user-id"
    m.body = body
    from datetime import datetime
    m.created_at = datetime(2026, 6, 6, 14, 5, 0)
    return m


class TestCreateTicket:
    def test_create_normal(self, client, override_db):
        ticket = _mock_ticket()
        with patch("app.api.support.create_ticket", new=AsyncMock(return_value=ticket)):
            r = client.post("/tickets", json={
                "subject": "无法登录",
                "body": "登录后白屏",
                "priority": "high",
            })
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        assert data["id"] == "t-1"
        assert data["subject"] == "测试工单"
        assert data["priority"] == "normal"

    def test_create_missing_subject_400(self, client, override_db):
        r = client.post("/tickets", json={"body": "x"})
        assert r.status_code == 422


class TestListTickets:
    def test_list(self, client, override_db):
        t1 = _mock_ticket("t-1")
        t2 = _mock_ticket("t-2", status="pending_customer")
        with patch("app.api.support.list_tickets", new=AsyncMock(return_value=[t1, t2])):
            r = client.get("/tickets")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 2
        assert data[0]["id"] == "t-1"

    def test_list_filter_status(self, client, override_db):
        with patch("app.api.support.list_tickets", new=AsyncMock(return_value=[])) as m:
            r = client.get("/tickets?status=resolved")
        assert r.status_code == 200
        assert m.await_args.kwargs["status"].value == "resolved"


class TestTicketDetail:
    def test_get_with_messages(self, client, override_db):
        t = _mock_ticket()
        m1 = _mock_message("m-1", "首次提交")
        m2 = _mock_message("m-2", "已解决")
        with patch(
            "app.api.support.get_ticket_with_messages",
            new=AsyncMock(return_value=(t, [m1, m2])),
        ):
            r = client.get("/tickets/t-1")
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["ticket"]["id"] == "t-1"
        assert len(body["messages"]) == 2

    def test_get_404(self, client, override_db):
        from app.services.support import TicketError
        with patch(
            "app.api.support.get_ticket_with_messages",
            new=AsyncMock(side_effect=TicketError("ticket not found")),
        ):
            r = client.get("/tickets/missing")
        assert r.status_code == 404


class TestReply:
    def test_reply(self, client, override_db):
        t = _mock_ticket()
        m = _mock_message("m-new", "补充信息")
        with patch("app.api.support.get_ticket_with_messages", new=AsyncMock(return_value=(t, []))):
            with patch("app.api.support.add_message", new=AsyncMock(return_value=m)):
                r = client.post("/tickets/t-1/messages", json={"body": "补充信息"})
        assert r.status_code == 201
        assert r.json()["data"]["body"] == "补充信息"


class TestClose:
    def test_close(self, client, override_db):
        t = _mock_ticket(status="closed")
        with patch("app.api.support.get_ticket_with_messages", new=AsyncMock(return_value=(t, []))):
            with patch("app.api.support.close_ticket", new=AsyncMock(return_value=t)):
                r = client.post("/tickets/t-1/close")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "closed"
