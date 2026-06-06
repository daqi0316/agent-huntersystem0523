"""P6-8 钉钉: 扫码登录 service — mock 模式 (无 corp_id 不阻塞)。

mock_mode=True (默认):
- generate_qrcode 返 mock 登录 URL
- exchange_code 用 code derive mock user (code="mock-{uuid}" → 派生 user_info)

mock_mode=False (DINGTALK_CORP_ID/AGENT_ID/APP_SECRET 配齐后启用):
- generate_qrcode 拼钉钉 OAuth URL: https://oapi.dingtalk.com/connect/oauth2/sns_authorize
- exchange_code 调 https://oapi.dingtalk.com/sns/getuserinfo_bycode 换 user_info
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dingtalk_oauth_state import DingtalkOAuthState


class DingtalkOAuthError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_mock() -> bool:
    return not (settings.dingtalk_corp_id and settings.dingtalk_agent_id and settings.dingtalk_app_secret)


async def generate_qrcode(
    db: AsyncSession, redirect_uri: str | None = None
) -> dict:
    """生成二维码 state + URL。

    Returns: {qrcode_url, state, expires_in, mock}
    """
    state = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(minutes=10)

    record = DingtalkOAuthState(
        state=state,
        redirect_uri=redirect_uri or "https://airecruit.com/oauth/dingtalk/callback",
        expires_at=expires_at,
    )
    db.add(record)
    await db.commit()

    if _is_mock():
        return {
            "qrcode_url": f"https://airecruit.com/mock/dingtalk/qr?state={state}",
            "state": state,
            "expires_in": 600,
            "mock": True,
            "hint": "Mock mode: 钉钉凭据未配置, 前端可展示 mock 二维码。code 需传 'mock-<state>' 走 mock 流程。",
        }

    url = (
        f"https://oapi.dingtalk.com/connect/oauth2/sns_authorize"
        f"?appid={settings.dingtalk_corp_id}"
        f"&response_type=code"
        f"&scope=snsapi_login"
        f"&state={state}"
        f"&redirect_uri={record.redirect_uri}"
    )
    return {
        "qrcode_url": url,
        "state": state,
        "expires_in": 600,
        "mock": False,
    }


async def exchange_code(db: AsyncSession, code: str, state: str) -> dict:
    """用 code + state 换钉钉 user_info。

    Mock: code == "mock-<state>" → 派生 mock user (unionid=dingtalk-mock-{uuid})
    Real: 调钉钉 API 拿 unionid + nickname
    """
    rec = (await db.execute(
        select(DingtalkOAuthState).where(DingtalkOAuthState.state == state)
    )).scalar_one_or_none()
    if rec is None:
        raise DingtalkOAuthError("invalid state")
    if rec.used_at is not None:
        raise DingtalkOAuthError("state already used")
    if rec.expires_at < _now():
        raise DingtalkOAuthError("state expired")
    rec.used_at = _now()

    if _is_mock():
        if not code.startswith("mock-"):
            raise DingtalkOAuthError("mock mode requires code=mock-<anything>")
        mock_unionid = f"dingtalk-mock-{uuid.uuid4().hex[:8]}"
        return {
            "mock": True,
            "unionid": mock_unionid,
            "openid": mock_unionid,
            "nickname": f"钉钉用户_{mock_unionid[-6:]}",
            "avatar": None,
            "raw": {"code": code, "state": state, "note": "mock derive"},
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            "https://oapi.dingtalk.com/sns/getuserinfo_bycode",
            params={"accessKey": settings.dingtalk_app_secret, "code": code},
        )
        if token_resp.status_code != 200:
            raise DingtalkOAuthError(f"dingtalk getuserinfo failed: {token_resp.text}")
        data = token_resp.json()
        if data.get("errcode", 0) != 0:
            raise DingtalkOAuthError(f"dingtalk errcode={data.get('errcode')} errmsg={data.get('errmsg')}")
        info = data.get("user_info", {})
        return {
            "mock": False,
            "unionid": info.get("unionid"),
            "openid": info.get("openid"),
            "nickname": info.get("nick"),
            "avatar": None,
            "raw": info,
        }
