"""P6-5 D3: 短信触达 API — 2 endpoint (手动 / 试用到期触发, 仅 Admin)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.notification import NotificationType
from app.services.notification_sms import (
    send_notification_sms,
    send_trial_expiring_sms,
)

router = APIRouter()


class SmsBody(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    notification_type: NotificationType
    title: str = Field(..., min_length=1, max_length=64)
    body: str = Field(..., min_length=1, max_length=512)


class TrialExpiringBody(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    days_left: int = Field(default=3, ge=1, le=30)


def _require_admin(org_ctx: OrgContext) -> None:
    if org_ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "only admin/owner can trigger SMS")


@router.post("/notifications/sms")
async def trigger_sms(
    body: SmsBody,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    _require_admin(org_ctx)
    return success(await send_notification_sms(
        db,
        user_id=org_ctx.user_id,
        org_id=org_ctx.org_id,
        phone=body.phone,
        notification_type=body.notification_type,
        title=body.title,
        body=body.body,
    ))


@router.post("/notifications/sms/trial-expiring")
async def trigger_trial_expiring_sms(
    body: TrialExpiringBody,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    _require_admin(org_ctx)
    return success(await send_trial_expiring_sms(
        db,
        user_id=org_ctx.user_id,
        org_id=org_ctx.org_id,
        phone=body.phone,
        days_left=body.days_left,
    ))
