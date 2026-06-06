"""P6-8 钉钉 OAuth API — 2 endpoint (login QR / callback)。

mock 模式默认启用 — 无 corp_id 不阻塞。等用户拿到钉钉开放平台凭据后
设置 DINGTALK_CORP_ID/AGENT_ID/APP_SECRET 自动切真模式。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success
from app.services.dingtalk_oauth import (
    DingtalkOAuthError,
    exchange_code,
    generate_qrcode,
)

router = APIRouter()


class CallbackResponse(BaseModel):
    mock: bool
    unionid: str
    openid: str
    nickname: str
    avatar: str | None = None
    next_step: str = "前端: 调 /api/v1/auth/login/dingtalk 携带 unionid 创/绑用户"


@router.get("/dingtalk/login")
async def dingtalk_login(
    redirect_uri: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """生成钉钉扫码登录二维码 URL + state。"""
    result = await generate_qrcode(db, redirect_uri=redirect_uri)
    return success(result)


@router.get("/dingtalk/callback")
async def dingtalk_callback(
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    """钉钉回调 — 用 code 换 user_info。"""
    try:
        info = await exchange_code(db, code=code, state=state)
    except DingtalkOAuthError as e:
        raise HTTPException(400, str(e))
    return success(CallbackResponse(**info).model_dump())
