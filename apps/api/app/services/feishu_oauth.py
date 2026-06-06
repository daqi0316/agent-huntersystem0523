"""P6-8 飞书 OAuth — mock 默认 + 真模式 (FEISHU_APP_ID/SECRET 配齐后自动切)。"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.feishu_oauth_state import FeishuOAuthState


class FeishuOAuthError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_mock() -> bool:
    return not (settings.feishu_app_id and settings.feishu_app_secret)


async def generate_qrcode(db: AsyncSession, redirect_uri: str | None = None) -> dict:
    state = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(minutes=10)
    rec = FeishuOAuthState(
        state=state,
        redirect_uri=redirect_uri or settings.feishu_oauth_redirect_uri,
        expires_at=expires_at,
    )
    db.add(rec)
    await db.commit()

    if _is_mock():
        return {
            "qrcode_url": f"https://airecruit.com/mock/feishu/qr?state={state}",
            "state": state,
            "expires_in": 600,
            "mock": True,
            "hint": "Mock mode: 飞书凭据未配置。code 需传 'mock-<state>'。",
        }

    url = (
        f"https://open.feishu.cn/open-apis/authen/v1/index"
        f"?app_id={settings.feishu_app_id}"
        f"&redirect_uri={rec.redirect_uri}"
        f"&state={state}"
        f"&scope=contact:user.id:readonly"
    )
    return {"qrcode_url": url, "state": state, "expires_in": 600, "mock": False}


async def exchange_code(db: AsyncSession, code: str, state: str) -> dict:
    rec = (await db.execute(
        select(FeishuOAuthState).where(FeishuOAuthState.state == state)
    )).scalar_one_or_none()
    if rec is None:
        raise FeishuOAuthError("invalid state")
    if rec.used_at is not None:
        raise FeishuOAuthError("state already used")
    if rec.expires_at < _now():
        raise FeishuOAuthError("state expired")
    rec.used_at = _now()

    if _is_mock():
        if not code.startswith("mock-"):
            raise FeishuOAuthError("mock mode requires code=mock-<anything>")
        mock_openid = f"feishu-mock-{uuid.uuid4().hex[:8]}"
        return {
            "mock": True,
            "open_id": mock_openid,
            "union_id": mock_openid,
            "name": f"飞书用户_{mock_openid[-6:]}",
            "avatar_url": None,
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            "https://open.feishu.cn/open-apis/authen/v1/access_token",
            json={"grant_type": "authorization_code", "code": code},
            headers={"Authorization": f"Bearer {settings.feishu_app_id}"},
        )
        if token_resp.status_code != 200:
            raise FeishuOAuthError(f"feishu access_token failed: {token_resp.text}")
        data = token_resp.json()
        if data.get("code", 0) != 0:
            raise FeishuOAuthError(f"feishu errcode={data.get('code')} msg={data.get('msg')}")
        info = data.get("data", {})
        return {
            "mock": False,
            "open_id": info.get("open_id"),
            "union_id": info.get("union_id"),
            "name": info.get("name"),
            "avatar_url": info.get("avatar_url"),
        }
