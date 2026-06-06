"""P5 in-app notification tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.notification import router
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


class TestNotificationEnum:
    def test_12_types(self):
        from app.models.notification import NotificationType
        assert len(NotificationType) == 12

    def test_onboarding_enums(self):
        from app.models.notification import NotificationType
        assert NotificationType.ONBOARDING_DAY1.value == "onboarding_day1"
        assert NotificationType.ONBOARDING_DAY14.value == "onboarding_day14"

    def test_payment_enums(self):
        from app.models.notification import NotificationType
        assert NotificationType.PAYMENT_SUCCESS.value == "payment_success"
        assert NotificationType.PAYMENT_FAILED.value == "payment_failed"


class TestNotificationEndpoints:
    def test_list_notifications(self, client, override_db, mock_db):
        from app.models.notification import Notification, NotificationType

        n = MagicMock()
        n.id = "n-1"
        n.type = NotificationType.ONBOARDING_DAY1
        n.title = "欢迎"
        n.body = "测试"
        n.link = "/onboarding"
        n.read = False
        n.read_at = None
        n.created_at = datetime.now(timezone.utc)

        with patch("app.api.notification.list_notifications", new=AsyncMock(return_value=[n])):
            resp = client.get("/notifications")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["read"] is False

    def test_unread_count(self, client, override_db, mock_db):
        with patch("app.api.notification.count_unread", new=AsyncMock(return_value=5)):
            resp = client.get("/notifications/unread-count")
        assert resp.json()["data"]["unread"] == 5

    def test_mark_read_404(self, client, override_db, mock_db):
        with patch("app.api.notification.mark_read", new=AsyncMock(return_value=None)):
            resp = client.post("/notifications/non-existent/read")
        assert resp.status_code == 404

    def test_mark_all_read(self, client, override_db, mock_db):
        with patch("app.api.notification.mark_all_read", new=AsyncMock(return_value=10)):
            resp = client.post("/notifications/read-all")
        assert resp.json()["data"]["marked_read"] == 10


class TestOnboardingTemplates:
    def test_4_templates(self):
        from app.services.notification import ONBOARDING_TEMPLATES
        assert len(ONBOARDING_TEMPLATES) == 4
        assert "day1" in ONBOARDING_TEMPLATES
        assert "day3" in ONBOARDING_TEMPLATES
        assert "day7" in ONBOARDING_TEMPLATES
        assert "day14" in ONBOARDING_TEMPLATES
