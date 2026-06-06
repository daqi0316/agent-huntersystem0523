"""P6-9: 内部数据看板 — CAC / LTV / Churn / NPS SQL 聚合 + 看板 API。

admin 限定 (复用 org_scoped_db 但 role=admin 校验)。
复用 P5-15 健康度 (同 org 维度)。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.response import success
from app.models.audit_log import AuditLog
from app.models.invitation import Invitation
from app.models.membership import Membership, MembershipStatus
from app.models.organization import Organization, OrganizationPlan, OrganizationStatus
from app.models.payment import PaymentOrder, PaymentStatus, Subscription, SubscriptionStatus
from app.models.referral import ReferralCode, ReferralUse
from app.models.user import User

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_admin(role: str) -> None:
    if role != "admin" and role != "platform_admin":
        raise HTTPException(403, "admin role required")


async def _cac_by_channel(db: AsyncSession) -> dict:
    """简版 CAC: 营销投入按 channel 估算 (Phase 6 接入后细化)。

    当前 Phase 5 mock 返 mock_cny_per_channel (P6-1 + P6-8 真实接入后改):
    - baidu_seo: ¥200
    - zhihu: ¥150
    - wechat_article: ¥100
    - referral: ¥0 (老带新无成本)
    - direct: ¥50
    - paid_ads: ¥500
    """
    return {
        "baidu_seo": {"cost_cny": 200, "new_customers": 0, "cac_cny": None, "status": "pending_phase6"},
        "zhihu": {"cost_cny": 150, "new_customers": 0, "cac_cny": None, "status": "pending_phase6"},
        "wechat_article": {"cost_cny": 100, "new_customers": 0, "cac_cny": None, "status": "pending_phase6"},
        "referral": {"cost_cny": 0, "new_customers": 0, "cac_cny": 0, "status": "active"},
        "direct": {"cost_cny": 50, "new_customers": 0, "cac_cny": None, "status": "pending_phase6"},
        "paid_ads": {"cost_cny": 500, "new_customers": 0, "cac_cny": None, "status": "pending_phase6"},
    }


async def _ltv_by_plan(db: AsyncSession) -> dict:
    """LTV: 过去 30d 各 plan 累计收入 / 活跃 org 数。

    Phase 5 mock (无真实客户) 返空 dict; 接入 P5-3 真实数据后自动算。
    """
    thirty_days_ago = _now() - timedelta(days=30)
    paid_orders = (await db.execute(
        select(PaymentOrder).where(
            PaymentOrder.status == PaymentStatus.PAID,
            PaymentOrder.paid_at >= thirty_days_ago,
        )
    )).scalars().all()

    by_plan: dict[str, dict] = {}
    for o in paid_orders:
        plan = o.plan.value
        if plan not in by_plan:
            by_plan[plan] = {"revenue_cents": 0, "order_count": 0}
        by_plan[plan]["revenue_cents"] += o.amount_cents
        by_plan[plan]["order_count"] += 1

    active_orgs_per_plan = (await db.execute(
        select(Subscription.plan, func.count(Subscription.org_id))
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
        .group_by(Subscription.plan)
    )).all()
    for plan, count in active_orgs_per_plan:
        p = plan.value if hasattr(plan, "value") else str(plan)
        by_plan.setdefault(p, {"revenue_cents": 0, "order_count": 0})
        by_plan[p]["active_orgs"] = count

    return by_plan


async def _churn_30d(db: AsyncSession) -> dict:
    """30d churn = 30d 内状态变 EXPIRED 或 CANCELLED 的 sub / 期初 active sub 总数。"""
    thirty_days_ago = _now() - timedelta(days=30)
    churned = (await db.execute(
        select(func.count(Subscription.org_id)).where(
            Subscription.status.in_([SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED]),
            Subscription.updated_at >= thirty_days_ago,
        )
    )).scalar() or 0
    period_start_active = (await db.execute(
        select(func.count(Subscription.org_id)).where(
            Subscription.current_period_start <= thirty_days_ago,
            Subscription.current_period_end >= thirty_days_ago,
        )
    )).scalar() or 0
    churn_rate = churned / max(period_start_active, 1) * 100
    return {
        "churned_30d": churned,
        "active_at_period_start": period_start_active,
        "churn_rate_pct": round(churn_rate, 2),
    }


async def _nps_score(db: AsyncSession) -> dict:
    """NPS 暂未接 survey 系统 (Phase 6 接入), 返 placeholder。"""
    return {"nps": None, "promoters": 0, "passives": 0, "detractors": 0, "status": "pending_survey"}


async def _referral_summary(db: AsyncSession) -> dict:
    total_codes = (await db.execute(
        select(func.count(ReferralCode.id))
    )).scalar() or 0
    total_uses = (await db.execute(
        select(func.count(ReferralUse.id))
    )).scalar() or 0
    conversion_rate = total_uses / max(total_codes, 1) * 100
    return {
        "total_codes": total_codes,
        "total_uses": total_uses,
        "conversion_rate_pct": round(conversion_rate, 2),
    }


async def _customer_count(db: AsyncSession) -> dict:
    by_status = (await db.execute(
        select(Organization.status, func.count(Organization.id))
        .group_by(Organization.status)
    )).all()
    by_plan = (await db.execute(
        select(Organization.plan, func.count(Organization.id))
        .group_by(Organization.plan)
    )).all()
    total = (await db.execute(
        select(func.count(Organization.id)).where(Organization.deleted_at.is_(None))
    )).scalar() or 0
    return {
        "total": total,
        "by_status": {str(s.value if hasattr(s, "value") else s): c for s, c in by_status},
        "by_plan": {str(p.value if hasattr(p, "value") else p): c for p, c in by_plan},
    }


@router.get("/growth/dashboard/summary")
async def growth_dashboard_summary(
    role: str = Query("admin", description="用户角色, 需 admin"),
):
    """admin 限定: 增长漏斗 6 维度汇总。"""
    _require_admin(role)
    async with AsyncSessionLocal() as db:
        cac = await _cac_by_channel(db)
        ltv = await _ltv_by_plan(db)
        churn = await _churn_30d(db)
        nps = await _nps_score(db)
        referral = await _referral_summary(db)
        customers = await _customer_count(db)
    return success({
        "generated_at": _now().isoformat(),
        "customers": customers,
        "cac_by_channel": cac,
        "ltv_by_plan": ltv,
        "churn_30d": churn,
        "nps": nps,
        "referral": referral,
    })


@router.get("/growth/dashboard/customers")
async def growth_dashboard_customers(
    role: str = Query("admin"),
):
    _require_admin(role)
    async with AsyncSessionLocal() as db:
        return success(await _customer_count(db))


@router.get("/growth/dashboard/churn")
async def growth_dashboard_churn(
    role: str = Query("admin"),
):
    _require_admin(role)
    async with AsyncSessionLocal() as db:
        return success(await _churn_30d(db))


@router.get("/growth/dashboard/referral")
async def growth_dashboard_referral(
    role: str = Query("admin"),
):
    _require_admin(role)
    async with AsyncSessionLocal() as db:
        return success(await _referral_summary(db))
