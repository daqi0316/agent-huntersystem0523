"""P5-2: 微信扫码登录 service + endpoint tests (mock 模式)。

不走 asyncio_run — 走 endpoint layer (TestClient + patch) 和直接 sync 调用。
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.auth import router
    _app.include_router(router, prefix="/api/v1/auth")
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

    async def _mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


class TestAuditLogEnum:
    def test_wechat_login_enum_value(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.WECHAT_LOGIN.value == "wechat_login"

    def test_wechat_bind_enum_value(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.WECHAT_BIND.value == "wechat_bind"


class TestConfig:
    def test_wechat_mock_mode_default_true(self):
        from app.core.config import settings
        assert settings.wechat_mock_mode is True

    def test_wechat_corp_id_default_empty(self):
        from app.core.config import settings
        assert settings.wechat_corp_id == ""

    def test_wechat_qrcode_expire_default_600(self):
        from app.core.config import settings
        assert settings.wechat_qrcode_expire_seconds == 600

    def test_wechat_redirect_uri_default(self):
        from app.core.config import settings
        assert "wechat/callback" in settings.wechat_oauth_redirect_uri


class TestQrcodeEndpoint:
    ROUTE = "/api/v1/auth/wechat/qrcode"

    def test_mock_mode_returns_state(self, client, override_db, mock_db):
        with patch("app.api.auth.generate_qrcode", new=AsyncMock(return_value={
            "qrcode_url": "weixin://mock?state=abc",
            "state": "abc",
            "expires_in": 600,
            "mock": True,
        })):
            resp = client.get(self.ROUTE)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["state"] == "abc"
        assert data["mock"] is True
        assert data["expires_in"] == 600


class TestMockLoginEndpoint:
    ROUTE = "/api/v1/auth/wechat/mock-login"

    def test_disabled_when_mock_mode_false(self, client, override_db, mock_db):
        with patch("app.core.config.settings.wechat_mock_mode", False):
            resp = client.post(f"{self.ROUTE}?code=any")
        assert resp.status_code == 403

    def test_returns_token_when_mock_mode(self, client, override_db, mock_db):
        mock_user = MagicMock()
        mock_user.id = "wx-user-1"
        mock_user.role.value = "hr"

        with patch("app.core.config.settings.wechat_mock_mode", True), \
             patch("app.api.auth.generate_qrcode", new=AsyncMock(return_value={
                 "qrcode_url": "x", "state": "s1", "expires_in": 600, "mock": True,
             })), \
             patch("app.api.auth.exchange_code", new=AsyncMock(return_value={
                 "unionid": "u1", "openid": "o1", "nickname": "n", "avatar_url": "a",
             })), \
             patch("app.api.auth.find_or_create_user", new=AsyncMock(return_value=mock_user)), \
             patch("app.api.auth.get_or_create_default_org", new=AsyncMock(return_value="org-1")):
            resp = client.post(f"{self.ROUTE}?code=mockcode_001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["org_id"] == "org-1"
        assert data["user_id"] == "wx-user-1"
        assert data["mock"] is True
        assert data["unionid"] == "u1"


class TestExchangeCodeDirectly:
    """exchange_code 走 AsyncMock 测, async def 模式 (pytest-asyncio)。"""

    @pytest.mark.asyncio
    async def test_invalid_state_raises(self):
        from app.services.wechat_oauth import exchange_code, WeChatOAuthError

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result_mock)

        with patch("app.core.config.settings.wechat_mock_mode", True):
            with pytest.raises(WeChatOAuthError, match="invalid state"):
                await exchange_code(db, code="c", state="missing")

    @pytest.mark.asyncio
    async def test_used_state_raises(self):
        from app.services.wechat_oauth import exchange_code, WeChatOAuthError

        record = MagicMock()
        record.used_at = datetime.now(timezone.utc)
        record.expires_at = datetime.now(timezone.utc).replace(year=2099)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=record)
        db.execute = AsyncMock(return_value=result_mock)

        with patch("app.core.config.settings.wechat_mock_mode", True):
            with pytest.raises(WeChatOAuthError, match="already used"):
                await exchange_code(db, code="c", state="used")


class TestFindOrCreateUserDirectly:
    @pytest.mark.asyncio
    async def test_existing_user_returned(self):
        from app.services.wechat_oauth import find_or_create_user

        db = AsyncMock()
        existing = MagicMock()
        existing.wechat_nickname = "old"
        existing.wechat_avatar_url = "old_url"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=existing)
        db.execute = AsyncMock(return_value=result_mock)

        user = await find_or_create_user(
            db, unionid="u1", openid="o1", nickname="new", avatar_url="new_url"
        )
        assert user is existing

    @pytest.mark.asyncio
    async def test_missing_unionid_raises(self):
        from app.services.wechat_oauth import find_or_create_user, WeChatOAuthError

        db = AsyncMock()
        with pytest.raises(WeChatOAuthError, match="unionid required"):
            await find_or_create_user(
                db, unionid="", openid="o", nickname="n", avatar_url="a"
            )
