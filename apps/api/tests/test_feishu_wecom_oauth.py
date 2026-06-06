"""P6-8 飞书 + 企微 OAuth — 4 endpoint 测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.feishu_wecom_oauth import router
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


def _fake_feishu_qr():
    return {
        "qrcode_url": "https://airecruit.com/mock/feishu/qr?state=test-state",
        "state": "test-state",
        "expires_in": 600,
        "mock": True,
        "hint": "Mock mode",
    }


def _fake_feishu_exchange():
    return {
        "mock": True,
        "open_id": "feishu-mock-12345678",
        "union_id": "feishu-mock-12345678",
        "name": "飞书用户_12345678",
        "avatar_url": None,
    }


def _fake_wecom_qr():
    return {
        "qrcode_url": "https://airecruit.com/mock/wecom/qr?state=test-state",
        "state": "test-state",
        "expires_in": 600,
        "mock": True,
        "hint": "Mock mode",
    }


def _fake_wecom_exchange():
    return {
        "mock": True,
        "userid": "wecom-mock-12345678",
        "name": "企微用户_12345678",
        "avatar": None,
    }


class TestFeishu:
    def test_login(self, client):
        with patch("app.api.feishu_wecom_oauth.feishu_qr", new=AsyncMock(return_value=_fake_feishu_qr())):
            r = client.get("/feishu/login")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mock"] is True
        assert data["state"] == "test-state"

    def test_callback(self, client):
        with patch("app.api.feishu_wecom_oauth.feishu_exchange", new=AsyncMock(return_value=_fake_feishu_exchange())):
            r = client.get("/feishu/callback?code=mock-test&state=test-state")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mock"] is True
        assert data["open_id"].startswith("feishu-mock-")
        assert data["name"].startswith("飞书用户_")

    def test_callback_invalid_state_400(self, client):
        from app.services.feishu_oauth import FeishuOAuthError
        with patch(
            "app.api.feishu_wecom_oauth.feishu_exchange",
            new=AsyncMock(side_effect=FeishuOAuthError("invalid state")),
        ):
            r = client.get("/feishu/callback?code=mock-test&state=bad")
        assert r.status_code == 400


class TestWecom:
    def test_login(self, client):
        with patch("app.api.feishu_wecom_oauth.wecom_qr", new=AsyncMock(return_value=_fake_wecom_qr())):
            r = client.get("/wecom/login")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mock"] is True

    def test_callback(self, client):
        with patch("app.api.feishu_wecom_oauth.wecom_exchange", new=AsyncMock(return_value=_fake_wecom_exchange())):
            r = client.get("/wecom/callback?code=mock-test&state=test-state")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["mock"] is True
        assert data["userid"].startswith("wecom-mock-")
        assert data["name"].startswith("企微用户_")

    def test_callback_invalid_state_400(self, client):
        from app.services.wecom_oauth import WecomOAuthError
        with patch(
            "app.api.feishu_wecom_oauth.wecom_exchange",
            new=AsyncMock(side_effect=WecomOAuthError("invalid state")),
        ):
            r = client.get("/wecom/callback?code=mock-test&state=bad")
        assert r.status_code == 400


class TestServiceMockMode:
    def test_feishu_mock_detected(self):
        from app.core.config import settings
        from app.services.feishu_oauth import _is_mock
        settings.feishu_app_id = ""
        settings.feishu_app_secret = ""
        assert _is_mock() is True
        settings.feishu_app_id = "x"
        settings.feishu_app_secret = "y"
        assert _is_mock() is False
        settings.feishu_app_id = ""
        settings.feishu_app_secret = ""

    def test_wecom_mock_detected(self):
        from app.core.config import settings
        from app.services.wecom_oauth import _is_mock
        settings.wecom_corp_id = ""
        settings.wecom_agent_id = ""
        settings.wecom_secret = ""
        assert _is_mock() is True
        settings.wecom_corp_id = "x"
        settings.wecom_agent_id = "y"
        settings.wecom_secret = "z"
        assert _is_mock() is False
        settings.wecom_corp_id = ""
        settings.wecom_agent_id = ""
        settings.wecom_secret = ""
