"""P6-8 钉钉 OAuth — 2 endpoint 测试 (login QR / callback)。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.dingtalk_oauth import router
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


def _fake_generate_qrcode(state: str = "test-state-abc"):
    return {
        "qrcode_url": f"https://airecruit.com/mock/dingtalk/qr?state={state}",
        "state": state,
        "expires_in": 600,
        "mock": True,
        "hint": "Mock mode: 钉钉凭据未配置",
    }


def _fake_exchange_code():
    return {
        "mock": True,
        "unionid": "dingtalk-mock-12345678",
        "openid": "dingtalk-mock-12345678",
        "nickname": "钉钉用户_12345678",
        "avatar": None,
        "raw": {"code": "mock-test", "state": "test-state-abc", "note": "mock derive"},
    }


class TestDingtalkLogin:
    def test_generate_qrcode_mock(self, client):
        with patch("app.api.dingtalk_oauth.generate_qrcode", new=AsyncMock(return_value=_fake_generate_qrcode())):
            r = client.get("/dingtalk/login")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mock"] is True
        assert data["state"] == "test-state-abc"
        assert "qrcode_url" in data
        assert data["expires_in"] == 600

    def test_generate_qrcode_with_redirect(self, client):
        with patch("app.api.dingtalk_oauth.generate_qrcode", new=AsyncMock(return_value=_fake_generate_qrcode())):
            r = client.get("/dingtalk/login?redirect_uri=https://example.com/callback")
        assert r.status_code == 200


class TestDingtalkCallback:
    def test_exchange_mock_code(self, client):
        with patch("app.api.dingtalk_oauth.exchange_code", new=AsyncMock(return_value=_fake_exchange_code())):
            r = client.get("/dingtalk/callback?code=mock-test&state=test-state-abc")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mock"] is True
        assert data["unionid"].startswith("dingtalk-mock-")
        assert data["nickname"].startswith("钉钉用户_")

    def test_exchange_invalid_state_400(self, client):
        from app.services.dingtalk_oauth import DingtalkOAuthError
        with patch(
            "app.api.dingtalk_oauth.exchange_code",
            new=AsyncMock(side_effect=DingtalkOAuthError("invalid state")),
        ):
            r = client.get("/dingtalk/callback?code=mock-test&state=bad")
        assert r.status_code == 400
        assert "state" in r.json()["detail"].lower()

    def test_exchange_missing_code_422(self, client):
        r = client.get("/dingtalk/callback?state=test")
        assert r.status_code == 422


class TestServiceMockMode:
    def test_mock_mode_detected(self):
        from app.core.config import settings
        from app.services.dingtalk_oauth import _is_mock
        settings.dingtalk_corp_id = ""
        settings.dingtalk_agent_id = ""
        settings.dingtalk_app_secret = ""
        assert _is_mock() is True

        settings.dingtalk_corp_id = "test_corp"
        settings.dingtalk_agent_id = "test_agent"
        settings.dingtalk_app_secret = "test_secret"
        assert _is_mock() is False

        settings.dingtalk_corp_id = ""
        settings.dingtalk_agent_id = ""
        settings.dingtalk_app_secret = ""
