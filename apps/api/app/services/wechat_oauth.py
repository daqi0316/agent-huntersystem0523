"""P5-2: 微信扫码登录 service。

mock_mode=True (默认):
- generate_qrcode 返假二维码 URL (前端展示用)
- exchange_code 用 code 直接 derive mock user_info (不调企微 API)
- 真凭据 (corp_id/agent_id/secret) 不需要

mock_mode=False:
- generate_qrcode 拼企微 OAuth URL: https://open.weixin.qq.com/connect/oauth2/authorize
- exchange_code 用 code 调 https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo 换 user_info
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User, UserRole
from app.models.wechat_oauth_state import WeChatOAuthState


class WeChatOAuthError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def generate_qrcode(db: AsyncSession, redirect_uri: str | None = None) -> dict:
    """生成二维码 state + URL。

    Returns: {qrcode_url, state, expires_in, mock}
    """
    state = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=settings.wechat_qrcode_expire_seconds)

    record = WeChatOAuthState(
        state=state,
        redirect_uri=redirect_uri or settings.wechat_oauth_redirect_uri,
        expires_at=expires_at,
    )
    db.add(record)
    await db.commit()

    if settings.wechat_mock_mode:
        qrcode_url = (
            f"weixin://wxpay/bizpayurl?pr=mockqrcode&state={state}"
        )
    else:
        qrcode_url = (
            "https://open.weixin.qq.com/connect/oauth2/authorize"
            f"?appid={settings.wechat_corp_id}"
            f"&redirect_uri={redirect_uri or settings.wechat_oauth_redirect_uri}"
            "&response_type=code&scope=snsapi_login"
            f"&state={state}#wechat_redirect"
        )

    return {
        "qrcode_url": qrcode_url,
        "state": state,
        "expires_in": settings.wechat_qrcode_expire_seconds,
        "mock": settings.wechat_mock_mode,
    }


async def exchange_code(db: AsyncSession, code: str, state: str) -> dict:
    """用 code + state 换 user_info。

    验 state: 未用过 + 未过期
    Returns: {unionid, openid, nickname, avatar_url}
    """
    record = (
        await db.execute(
            select(WeChatOAuthState).where(WeChatOAuthState.state == state)
        )
    ).scalar_one_or_none()
    if record is None:
        raise WeChatOAuthError("invalid state")
    if record.used_at is not None:
        raise WeChatOAuthError("state already used")
    if record.expires_at < _now():
        raise WeChatOAuthError("state expired")

    record.used_at = _now()
    await db.commit()

    if settings.wechat_mock_mode:
        if not code:
            raise WeChatOAuthError("mock mode requires code (any non-empty string)")
        return {
            "unionid": f"mock_unionid_{code[:8]}",
            "openid": f"mock_openid_{code[:8]}",
            "nickname": f"微信用户_{code[:6]}",
            "avatar_url": "https://thirdwx.qlogo.cn/mmopen/mock_avatar.png",
        }

    if not (settings.wechat_corp_id and settings.wechat_corp_secret):
        raise WeChatOAuthError("wechat credentials not configured")

    access_token_resp = await _fetch_access_token(code)
    access_token = access_token_resp.get("access_token")
    if not access_token:
        raise WeChatOAuthError(f"failed to get access_token: {access_token_resp}")

    user_info_resp = await _fetch_user_info(access_token, code)
    return {
        "unionid": user_info_resp.get("unionid") or user_info_resp.get("userid", ""),
        "openid": user_info_resp.get("openid", ""),
        "nickname": user_info_resp.get("name") or user_info_resp.get("nickname", "微信用户"),
        "avatar_url": user_info_resp.get("avatar", ""),
    }


async def _fetch_access_token(code: str) -> dict:
    url = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
    params = {
        "access_key": settings.wechat_corp_secret,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        return resp.json()


async def _fetch_user_info(access_token: str, code: str) -> dict:
    url = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserdetail"
    params = {
        "access_token": access_token,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        return resp.json()


async def find_or_create_user(
    db: AsyncSession,
    unionid: str,
    openid: str,
    nickname: str,
    avatar_url: str,
) -> User:
    """按 unionid 查 user, 无则建 + 设 auth_source='wechat'。"""
    if not unionid:
        raise WeChatOAuthError("unionid required")

    user = (
        await db.execute(select(User).where(User.wechat_unionid == unionid))
    ).scalar_one_or_none()

    if user is not None:
        if user.wechat_nickname != nickname:
            user.wechat_nickname = nickname
        if avatar_url and user.wechat_avatar_url != avatar_url:
            user.wechat_avatar_url = avatar_url
        user.last_login_at = _now()
        await db.commit()
        return user

    email = f"wx_{unionid}@wechat.local"
    placeholder_hash = "$wechat$" + secrets.token_hex(16)
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        hashed_password=placeholder_hash,
        name=nickname or "微信用户",
        role=UserRole.HR,
        wechat_unionid=unionid,
        wechat_openid=openid,
        wechat_nickname=nickname,
        wechat_avatar_url=avatar_url,
        auth_source="wechat",
        is_active=True,
        last_login_at=_now(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
