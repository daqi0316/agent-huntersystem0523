"""P6-5 D3: 阿里云短信触达 — 2 endpoint + 5 service 函数测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.notification_sms import router
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

    async def _mock_admin_ctx():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="owner"), mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[org_scoped_db] = _mock_admin_ctx
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(org_scoped_db, None)


@pytest.fixture
def override_hr_db(app, mock_db):
    from app.core.database import get_db
    from app.core.org_context import OrgContext, org_scoped_db

    async def _mock_get_db():
        yield mock_db

    async def _mock_hr_ctx():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[org_scoped_db] = _mock_hr_ctx
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(org_scoped_db, None)


class TestTriggerSms:
    def test_admin_can_trigger(self, client, override_db, mock_db):
        with patch("app.api.notification_sms.send_notification_sms",
                   new=AsyncMock(return_value={"ok": True, "mock": True, "phone": "13800000000"})):
            r = client.post("/notifications/sms", json={
                "phone": "13800000000",
                "notification_type": "trial_expiring",
                "title": "试用到期",
                "body": "3 天后到期",
            })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["ok"] is True
        assert data["mock"] is True

    def test_invalid_phone_422(self, client, override_db):
        r = client.post("/notifications/sms", json={
            "phone": "12345",
            "notification_type": "trial_expiring",
            "title": "试用到期",
            "body": "3 天后到期",
        })
        assert r.status_code == 422

    def test_hr_role_forbidden_403(self, client, override_hr_db):
        r = client.post("/notifications/sms", json={
            "phone": "13800000000",
            "notification_type": "trial_expiring",
            "title": "试用到期",
            "body": "3 天后到期",
        })
        assert r.status_code == 403


class TestTrialExpiring:
    def test_admin_trigger(self, client, override_db, mock_db):
        with patch("app.api.notification_sms.send_trial_expiring_sms",
                   new=AsyncMock(return_value={"ok": True, "mock": True, "days_left": 3})):
            r = client.post("/notifications/sms/trial-expiring", json={
                "phone": "13800000000",
                "days_left": 3,
            })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["ok"] is True

    def test_default_days_left(self, client, override_db):
        with patch("app.api.notification_sms.send_trial_expiring_sms",
                   new=AsyncMock(return_value={"ok": True, "mock": True})) as m:
            r = client.post("/notifications/sms/trial-expiring", json={"phone": "13800000000"})
        assert r.status_code == 200
        assert m.await_args.kwargs["days_left"] == 3


class TestServiceMockMode:
    def test_mock_detected(self):
        from app.core.config import settings
        from app.services.notification_sms import _is_mock
        settings.aliyun_access_key_id = ""
        settings.aliyun_access_key_secret = ""
        assert _is_mock() is True
        settings.aliyun_access_key_id = "ak"
        settings.aliyun_access_key_secret = "sk"
        assert _is_mock() is False
        settings.aliyun_access_key_id = ""
        settings.aliyun_access_key_secret = ""

    def test_send_notification_sms_mock(self):
        from app.core.config import settings
        from app.services.notification_sms import send_notification_sms
        from app.models.notification import NotificationType
        settings.aliyun_access_key_id = ""
        settings.aliyun_access_key_secret = ""

        db = AsyncMock()
        mock_notif = AsyncMock()
        mock_notif.id = "n-1"
        with patch("app.services.notification_sms.Notification", new=lambda **kw: mock_notif):
            import asyncio
            result = asyncio.run(send_notification_sms(
                db,
                user_id="u-1",
                org_id="o-1",
                phone="13800000000",
                notification_type=NotificationType.TRIAL_EXPIRING,
                title="测试",
                body="测试",
            ))
        assert result["ok"] is True
        assert result["mock"] is True
        assert result["phone"] == "13800000000"
