"""P6-5 D1+D2+D3: 触达渠道 API — 微信模板触发 (调试用, Admin only)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.services.wechat_template import (
    _is_mock,
    send_onboarding_d1_wechat,
    send_onboarding_d3_wechat,
    send_onboarding_d7_wechat,
    send_onboarding_d14_wechat,
)

router = APIRouter()


class WechatBody(BaseModel):
    openid: str = Field(..., min_length=1, max_length=128)
    day: int = Field(..., ge=1, le=14, description="触达日: 1/3/7/14")


@router.get("/notifications/wechat/status")
async def wechat_status(ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db)):
    org_ctx, db = ctx
    return success({
        "mock_mode": _is_mock(),
        "configured": not _is_mock(),
    })


@router.post("/notifications/wechat/onboarding")
async def trigger_onboarding_wechat(
    body: WechatBody,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    if org_ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "only admin/owner can trigger WeChat")
    if body.day == 1:
        result = await send_onboarding_d1_wechat(db, org_ctx.user_id, org_ctx.org_id, body.openid)
    elif body.day == 3:
        result = await send_onboarding_d3_wechat(db, org_ctx.user_id, org_ctx.org_id, body.openid)
    elif body.day == 7:
        result = await send_onboarding_d7_wechat(db, org_ctx.user_id, org_ctx.org_id, body.openid)
    elif body.day == 14:
        result = await send_onboarding_d14_wechat(db, org_ctx.user_id, org_ctx.org_id, body.openid)
    else:
        raise HTTPException(400, "day must be 1/3/7/14")
    return success(result)
