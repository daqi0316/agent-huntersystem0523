"""P6-8 飞书 + 企微 OAuth API — 共 4 endpoint。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success
from app.services.feishu_oauth import FeishuOAuthError, exchange_code as feishu_exchange, generate_qrcode as feishu_qr
from app.services.wecom_oauth import WecomOAuthError, exchange_code as wecom_exchange, generate_qrcode as wecom_qr

router = APIRouter()


class FeishuCallbackResponse(BaseModel):
    mock: bool
    open_id: str
    union_id: str
    name: str
    avatar_url: str | None = None


class WecomCallbackResponse(BaseModel):
    mock: bool
    userid: str
    name: str
    avatar: str | None = None


@router.get("/feishu/login")
async def feishu_login(
    redirect_uri: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return success(await feishu_qr(db, redirect_uri=redirect_uri))


@router.get("/feishu/callback")
async def feishu_callback(
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    try:
        info = await feishu_exchange(db, code=code, state=state)
    except FeishuOAuthError as e:
        raise HTTPException(400, str(e))
    return success(FeishuCallbackResponse(**info).model_dump())


@router.get("/wecom/login")
async def wecom_login(
    redirect_uri: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return success(await wecom_qr(db, redirect_uri=redirect_uri))


@router.get("/wecom/callback")
async def wecom_callback(
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    try:
        info = await wecom_exchange(db, code=code, state=state)
    except WecomOAuthError as e:
        raise HTTPException(400, str(e))
    return success(WecomCallbackResponse(**info).model_dump())
