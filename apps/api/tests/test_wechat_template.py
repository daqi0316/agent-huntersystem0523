"""P6-5 D2: 微信服务号模板消息 — service + 2 endpoint 测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.wechat_template import router
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


class TestWechatStatus:
    def test_status_mock(self, client, override_db):
        r = client.get("/notifications/wechat/status")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "mock_mode" in data
        assert "configured" in data


class TestTriggerOnboarding:
    def _mock_send_result(self, day: int, mock: bool = True):
        return {
            "ok": True,
            "mock": mock,
            "openid": "test-openid",
            "notification_id": f"n-d{day}",
            "template_id": "TEMPLATE_PENDING" if mock else "real-template-id",
        }

    def test_admin_trigger_d1(self, client, override_db, mock_db):
        with patch(
            "app.api.wechat_template.send_onboarding_d1_wechat",
            new=AsyncMock(return_value=self._mock_send_result(1)),
        ):
            r = client.post(
                "/notifications/wechat/onboarding",
                json={"openid": "test-openid", "day": 1},
            )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["ok"] is True
        assert data["mock"] is True

    def test_admin_trigger_d14(self, client, override_db):
        with patch(
            "app.api.wechat_template.send_onboarding_d14_wechat",
            new=AsyncMock(return_value=self._mock_send_result(14)),
        ):
            r = client.post(
                "/notifications/wechat/onboarding",
                json={"openid": "test-openid", "day": 14},
            )
        assert r.status_code == 200

    def test_invalid_day_400(self, client, override_db):
        r = client.post(
            "/notifications/wechat/onboarding",
            json={"openid": "test-openid", "day": 5},
        )
        assert r.status_code == 400

    def test_hr_forbidden_403(self, app, mock_db):
        from app.core.database import get_db
        from app.core.org_context import OrgContext, org_scoped_db

        async def _mock_get_db():
            yield mock_db

        async def _mock_hr_ctx():
            yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), mock_db

        app.dependency_overrides[get_db] = _mock_get_db
        app.dependency_overrides[org_scoped_db] = _mock_hr_ctx
        c = TestClient(app)
        r = c.post(
            "/notifications/wechat/onboarding",
            json={"openid": "test-openid", "day": 1},
        )
        assert r.status_code == 403


class TestServiceMockMode:
    def test_mock_detected(self):
        from app.core.config import settings
        from app.services.wechat_template import _is_mock
        settings.wechat_corp_id = ""
        settings.wechat_corp_secret = ""
        settings.wechat_template_id = ""
        assert _is_mock() is True
        settings.wechat_corp_id = "wx_corp"
        settings.wechat_corp_secret = "secret"
        settings.wechat_template_id = "tmpl-1"
        assert _is_mock() is False
        settings.wechat_corp_id = ""
        settings.wechat_corp_secret = ""
        settings.wechat_template_id = ""

    def test_send_wechat_template_mock(self):
        import asyncio
        from app.core.config import settings
        from app.services.wechat_template import send_wechat_template
        from app.models.notification import NotificationType
        settings.wechat_corp_id = ""
        settings.wechat_corp_secret = ""
        settings.wechat_template_id = ""

        db = AsyncMock()
        mock_notif = MagicMock()
        mock_notif.id = "n-1"
        with patch("app.services.wechat_template.Notification", new=lambda **kw: mock_notif):
            result = asyncio.run(send_wechat_template(
                db,
                user_id="u-1",
                org_id="o-1",
                openid="o-1",
                notification_type=NotificationType.ONBOARDING_DAY1,
                title="测试",
                body="测试",
            ))
        assert result["ok"] is True
        assert result["mock"] is True
