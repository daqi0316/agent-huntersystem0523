"""P6-8 企微 OAuth — mock 默认 + 真模式 (WECOM_CORP_ID/AGENT_ID/SECRET 配齐后自动切)。

企微与钉钉类似, 用 corp_id 区分企业, agent_id 区分自建应用。
扫码登录 URL: https://login.work.weixin.qq.com/wwlogin/sso/login
获取用户身份 URL: https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.wecom_oauth_state import WecomOAuthState


class WecomOAuthError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_mock() -> bool:
    return not (settings.wecom_corp_id and settings.wecom_agent_id and settings.wecom_secret)


async def generate_qrcode(db: AsyncSession, redirect_uri: str | None = None) -> dict:
    state = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(minutes=10)
    rec = WecomOAuthState(
        state=state,
        redirect_uri=redirect_uri or settings.wecom_oauth_redirect_uri,
        expires_at=expires_at,
    )
    db.add(rec)
    await db.commit()

    if _is_mock():
        return {
            "qrcode_url": f"https://airecruit.com/mock/wecom/qr?state={state}",
            "state": state,
            "expires_in": 600,
            "mock": True,
            "hint": "Mock mode: 企微凭据未配置。code 需传 'mock-<state>'。",
        }

    url = (
        f"https://login.work.weixin.qq.com/wwlogin/sso/login"
        f"?appid={settings.wecom_corp_id}"
        f"&agentid={settings.wecom_agent_id}"
        f"&state={state}"
        f"&redirect_uri={rec.redirect_uri}"
    )
    return {"qrcode_url": url, "state": state, "expires_in": 600, "mock": False}


async def exchange_code(db: AsyncSession, code: str, state: str) -> dict:
    rec = (await db.execute(
        select(WecomOAuthState).where(WecomOAuthState.state == state)
    )).scalar_one_or_none()
    if rec is None:
        raise WecomOAuthError("invalid state")
    if rec.used_at is not None:
        raise WecomOAuthError("state already used")
    if rec.expires_at < _now():
        raise WecomOAuthError("state expired")
    rec.used_at = _now()

    if _is_mock():
        if not code.startswith("mock-"):
            raise WecomOAuthError("mock mode requires code=mock-<anything>")
        mock_userid = f"wecom-mock-{uuid.uuid4().hex[:8]}"
        return {
            "mock": True,
            "userid": mock_userid,
            "name": f"企微用户_{mock_userid[-6:]}",
            "avatar": None,
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        user_resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo",
            params={"code": code},
        )
        if user_resp.status_code != 200:
            raise WecomOAuthError(f"wecom getuserinfo failed: {user_resp.text}")
        data = user_resp.json()
        if data.get("errcode", 0) != 0:
            raise WecomOAuthError(f"wecom errcode={data.get('errcode')} errmsg={data.get('errmsg')}")
        return {
            "mock": False,
            "userid": data.get("userid"),
            "name": data.get("name") or data.get("userid"),
            "avatar": data.get("avatar"),
        }
