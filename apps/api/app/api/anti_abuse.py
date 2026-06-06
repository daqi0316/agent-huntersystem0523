"""P5-11: 反垃圾/反滥用 API — 短信验证 + 设备指纹 + 邀请防刷 + LLM 熔断。"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.anti_abuse import SMS_CODE_LENGTH, SMS_CODE_TTL_MINUTES, SmsPurpose
from app.models.user import User
from app.services.anti_abuse import (
    AntiAbuseError,
    bind_phone_to_user,
    check_invite_rate_limit,
    compute_device_fingerprint,
    send_sms_code,
    validate_phone,
    verify_sms_code,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class SendSmsRequest(BaseModel):
    phone: str = Field(..., description="E.164 格式或中国 11 位, 如 13800138000")
    purpose: str = Field(SmsPurpose.REGISTER, description="register | login | reset_password | bind_phone")


class VerifySmsRequest(BaseModel):
    phone: str
    code: str = Field(..., min_length=SMS_CODE_LENGTH, max_length=SMS_CODE_LENGTH)
    purpose: str = Field(SmsPurpose.REGISTER)


class BindPhoneRequest(BaseModel):
    phone: str
    code: str = Field(..., min_length=SMS_CODE_LENGTH, max_length=SMS_CODE_LENGTH)


@router.post("/auth/send-sms-code", status_code=200)
async def send_sms(
    body: SendSmsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """发短信验证码 (公开端点, 仅防 1min 内 3 条刷屏)。"""
    if not validate_phone(body.phone):
        raise HTTPException(400, "invalid phone format")
    if body.purpose not in (SmsPurpose.REGISTER, SmsPurpose.LOGIN, SmsPurpose.RESET_PASSWORD, SmsPurpose.BIND_PHONE):
        raise HTTPException(400, f"invalid purpose: {body.purpose}")
    ip = request.client.host if request.client else None
    try:
        verification = await send_sms_code(db, body.phone, body.purpose, ip_address=ip)
    except AntiAbuseError as e:
        raise HTTPException(429, str(e))
    return success({
        "phone": verification.phone,
        "purpose": verification.purpose,
        "expires_at": verification.expires_at.isoformat(),
        "ttl_minutes": SMS_CODE_TTL_MINUTES,
        "code_length": SMS_CODE_LENGTH,
        "mock": True,
    })


@router.post("/auth/verify-sms-code", status_code=200)
async def verify_sms(
    body: VerifySmsRequest,
    db: AsyncSession = Depends(get_db),
):
    """验短信码 (公开, 仅返是否通过, 不动 user 表)。"""
    try:
        record = await verify_sms_code(db, body.phone, body.code, body.purpose)
    except AntiAbuseError as e:
        raise HTTPException(400, str(e))
    return success({
        "phone": record.phone,
        "purpose": record.purpose,
        "verified": True,
        "verified_at": record.used_at.isoformat() if record.used_at else None,
    })


@router.post("/auth/bind-phone", status_code=200)
async def bind_phone(
    body: BindPhoneRequest,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """绑手机到当前 user (1 手机 1 账号, 需先验短信码)。"""
    org_ctx, db = ctx
    if not validate_phone(body.phone):
        raise HTTPException(400, "invalid phone format")

    try:
        await verify_sms_code(db, body.phone, body.code, SmsPurpose.BIND_PHONE)
    except AntiAbuseError as e:
        raise HTTPException(400, f"sms verify failed: {e}")

    user = (await db.execute(
        __import__("sqlalchemy").select(User).where(User.id == org_ctx.user_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "user not found")

    try:
        user = await bind_phone_to_user(db, user, body.phone)
    except AntiAbuseError as e:
        raise HTTPException(409, str(e))

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.PHONE_BOUND,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"phone_masked": body.phone[:3] + "****" + body.phone[-2:]},
    )
    await db.commit()
    return success({
        "user_id": user.id,
        "phone_verified": user.phone_verified,
        "phone_verified_at": user.phone_verified_at.isoformat() if user.phone_verified_at else None,
    })


@router.get("/auth/device-fingerprint-status", status_code=200)
async def device_fingerprint_status(
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """看当前 org 当前 device 的邀请配额状态。"""
    org_ctx, db = ctx
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")
    fp = compute_device_fingerprint(ua, ip or "unknown")
    allowed, reason = await check_invite_rate_limit(db, org_ctx.org_id, ip, ua)
    return success({
        "fingerprint_hash": fp[:16] + "…",
        "ip_address": ip,
        "invite_allowed": allowed,
        "reason": reason,
    })


@router.post("/auth/llm-circuit-breaker-check", status_code=200)
async def llm_circuit_breaker_check(
    request: Request,
    body: dict,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """LLM token 熔断检查: 超 100% 时返 429。"""
    from app.services.anti_abuse import check_llm_circuit_breaker
    org_ctx, db = ctx
    plan = body.get("plan", "starter")
    allowed, remaining, limit = await check_llm_circuit_breaker(db, org_ctx.org_id, plan)
    if not allowed:
        from app.api.audit_logs import log_audit
        from app.models.audit_log import AuditLogAction
        await log_audit(
            db, org_id=org_ctx.org_id,
            action=AuditLogAction.LLM_CIRCUIT_BREAKER,
            actor_user_id=org_ctx.user_id,
            request=request,
            metadata={"plan": plan, "limit": limit},
        )
        await db.commit()
        raise HTTPException(429, {
            "success": False,
            "error": "llm_circuit_breaker",
            "message": f"LLM token 配额已用完, 升级 plan 或等下月初重置",
            "remaining": remaining,
            "limit": limit,
        })
    return success({
        "allowed": True,
        "remaining": remaining,
        "limit": limit,
    })
