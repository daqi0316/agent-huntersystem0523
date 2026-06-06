"""P6-3 + P6-4 API — trial 状态 + referral code 管理。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.services.referral import (
    create_referral_code,
    get_referral_code_for_org,
    grant_seat_reward,
    is_trial_active,
    list_referral_uses_for_org,
    redeem_referral_code,
    start_trial_for_org,
    trial_days_remaining,
)

router = APIRouter()


class RedeemReferralRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=16)


@router.get("/trial/status")
async def get_trial_status(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """查当前 org 的 trial 状态。"""
    org_ctx, db = ctx
    from app.services.payment import get_active_subscription
    sub = await get_active_subscription(db, org_ctx.org_id)
    if sub is None:
        return success({
            "trial_active": False,
            "trial_end_at": None,
            "days_remaining": 0,
            "plan": None,
        })
    return success({
        "trial_active": is_trial_active(sub),
        "trial_end_at": sub.trial_end_at.isoformat() if sub.trial_end_at else None,
        "days_remaining": trial_days_remaining(sub),
        "plan": sub.plan.value,
        "status": sub.status.value,
    })


@router.post("/trial/start")
async def start_trial(
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """self-serve: 启动 14 天 trial (已存在 sub 返现成)。"""
    org_ctx, db = ctx
    sub = await start_trial_for_org(db, org_ctx.org_id, org_ctx.user_id)
    return success({
        "trial_active": is_trial_active(sub),
        "trial_end_at": sub.trial_end_at.isoformat() if sub.trial_end_at else None,
        "days_remaining": trial_days_remaining(sub),
        "plan": sub.plan.value,
    })


@router.get("/referral/code")
async def my_referral_code(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """查自己 org 的 referral code (没有就生成)。"""
    org_ctx, db = ctx
    ref = await get_referral_code_for_org(db, org_ctx.org_id)
    if ref is None:
        ref = await create_referral_code(db, org_ctx.org_id, org_ctx.user_id)
    return success({
        "code": ref.code,
        "uses": ref.uses,
        "max_uses": ref.max_uses,
        "seat_reward": ref.seat_reward,
        "share_url": f"https://airecruit.com/signup?ref={ref.code}",
    })


@router.get("/referral/uses")
async def my_referral_uses(
    limit: int = Query(20, ge=1, le=100),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """查自己 org 推荐了谁。"""
    org_ctx, db = ctx
    rows = await list_referral_uses_for_org(db, org_ctx.org_id, limit)
    return success([
        {
            "new_org_id": r.new_org_id,
            "new_user_id": r.new_user_id,
            "ip_address": r.ip_address,
            "seat_rewarded": r.seat_rewarded,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ])


@router.post("/referral/redeem")
async def redeem_my_referral(
    body: RedeemReferralRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: str = Query(..., description="new_user_id (新注册用户)"),
    org_id: str = Query(..., description="new_org_id (新 org)"),
):
    """公开: 新用户用 referral code 注册, 双方 seat+1 奖励。

    实际生产中应在 /auth/register flow 内部调, 这里暴露成 endpoint 方便 e2e + 调试。
    """
    from app.core.dependencies import get_current_user_id
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")
    try:
        use = await redeem_referral_code(
            db, body.code, org_id, user_id, ip_address=ip, user_agent=ua,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    inviter_quota = await grant_seat_reward(db, use.inviter_org_id, seats=1)
    new_quota = await grant_seat_reward(db, use.new_org_id, seats=1)

    return success({
        "redeemed": True,
        "inviter_org_id": use.inviter_org_id,
        "new_org_id": use.new_org_id,
        "inviter_quota_after": inviter_quota,
        "new_quota_after": new_quota,
    })
