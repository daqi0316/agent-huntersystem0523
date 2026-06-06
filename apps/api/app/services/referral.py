"""P6-3 + P6-4 service — self-serve trial + 老带新 referral。"""
from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.organization import Organization, OrganizationPlan, OrganizationStatus
from app.models.payment import Subscription, SubscriptionStatus, PaymentPlan
from app.models.referral import ReferralCode, ReferralUse
from app.models.user import User


TRIAL_DAYS = 14
TRIAL_REMIND_DAYS_BEFORE = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    exclude = {"0", "O", "I", "1", "L"}
    chars = [c for c in alphabet if c not in exclude]
    return "".join(secrets.choice(chars) for _ in range(length))


async def start_trial_for_org(
    db: AsyncSession, org_id: str, user_id: str
) -> Subscription:
    """self-serve 注册: 14 天试用 starter (免费)。已存在 sub 直接返。"""
    from app.services.payment import get_active_subscription
    existing = await get_active_subscription(db, org_id)
    if existing is not None:
        return existing

    now = _now()
    sub = Subscription(
        id=str(uuid.uuid4()),
        org_id=org_id,
        plan=PaymentPlan.STARTER,
        billing_cycle="monthly",
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=TRIAL_DAYS),
        auto_renew=False,
        trial_end_at=now + timedelta(days=TRIAL_DAYS),
        trial_reminded=False,
    )
    db.add(sub)

    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    if org is not None:
        org.plan = OrganizationPlan.STARTER
        org.status = OrganizationStatus.TRIAL
        org.subscription_renews_at = sub.trial_end_at
    await db.commit()
    await db.refresh(sub)
    return sub


def is_trial_active(subscription: Subscription) -> bool:
    """trial 是否在 14 天内。"""
    if subscription.trial_end_at is None:
        return False
    return _now() < subscription.trial_end_at


def trial_days_remaining(subscription: Subscription) -> int:
    if subscription.trial_end_at is None:
        return 0
    delta = subscription.trial_end_at - _now()
    return max(0, delta.days)


def trial_should_remind(subscription: Subscription) -> bool:
    """trial 到期前 3 天且未提醒过时返 True。"""
    if subscription.trial_end_at is None:
        return False
    if subscription.trial_reminded:
        return False
    delta = subscription.trial_end_at - _now()
    return 0 < delta.days <= TRIAL_REMIND_DAYS_BEFORE


async def expire_overdue_trials(db: AsyncSession) -> int:
    """定时任务: trial 到期未付费的 sub 标 EXPIRED + 设 org READONLY 状态。"""
    from sqlalchemy import update as sa_update
    now = _now()
    expired_subs = (await db.execute(
        select(Subscription).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.trial_end_at.isnot(None),
            Subscription.trial_end_at < now,
        )
    )).scalars().all()
    for sub in expired_subs:
        sub.status = SubscriptionStatus.EXPIRED
    await db.commit()
    return len(expired_subs)


async def mark_trial_reminded(db: AsyncSession, subscription: Subscription) -> None:
    subscription.trial_reminded = True
    await db.commit()


async def create_referral_code(
    db: AsyncSession, org_id: str, user_id: str, max_uses: int = 100
) -> ReferralCode:
    """老带新: 给 org 生成一个 referral code (8 位大写字母数字)。"""
    existing = (await db.execute(
        select(ReferralCode).where(
            ReferralCode.org_id == org_id,
            ReferralCode.active == True,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    for _ in range(10):
        candidate = _generate_referral_code()
        existing_code = (await db.execute(
            select(ReferralCode).where(ReferralCode.code == candidate)
        )).scalar_one_or_none()
        if existing_code is None:
            break
    else:
        raise RuntimeError("failed to generate unique referral code")

    record = ReferralCode(
        id=str(uuid.uuid4()),
        org_id=org_id,
        code=candidate,
        created_by=user_id,
        max_uses=max_uses,
        seat_reward=1,
        active=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def redeem_referral_code(
    db: AsyncSession,
    code: str,
    new_org_id: str,
    new_user_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> ReferralUse:
    """新用户用 referral code 注册, 双方 seat+1 奖励。"""
    ref = (await db.execute(
        select(ReferralCode).where(
            ReferralCode.code == code,
            ReferralCode.active == True,
        )
    )).scalar_one_or_none()
    if ref is None:
        raise ValueError("invalid referral code")
    if ref.expires_at is not None and ref.expires_at < _now():
        raise ValueError("referral code expired")
    if ref.uses >= ref.max_uses:
        raise ValueError("referral code max uses reached")
    if ref.org_id == new_org_id:
        raise ValueError("cannot self-refer")

    existing = (await db.execute(
        select(ReferralUse).where(ReferralUse.new_org_id == new_org_id)
    )).scalar_one_or_none()
    if existing is not None:
        raise ValueError("new org already redeemed a referral code")

    use = ReferralUse(
        id=str(uuid.uuid4()),
        referral_code_id=ref.id,
        inviter_org_id=ref.org_id,
        new_org_id=new_org_id,
        new_user_id=new_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        seat_rewarded=True,
    )
    db.add(use)
    ref.uses = (ref.uses or 0) + 1
    await db.commit()
    await db.refresh(use)
    return use


async def grant_seat_reward(
    db: AsyncSession, org_id: str, seats: int = 1
) -> int:
    """老带新奖励: org 配额 +seats。返新配额值。"""
    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    if org is None:
        return 0
    org.quota_max_users = (org.quota_max_users or 0) + seats
    await db.commit()
    return org.quota_max_users


async def get_referral_code_for_org(
    db: AsyncSession, org_id: str
) -> Optional[ReferralCode]:
    return (await db.execute(
        select(ReferralCode).where(
            ReferralCode.org_id == org_id,
            ReferralCode.active == True,
        )
    )).scalar_one_or_none()


async def list_referral_uses_for_org(
    db: AsyncSession, org_id: str, limit: int = 20
) -> list[ReferralUse]:
    return (await db.execute(
        select(ReferralUse).where(
            ReferralUse.inviter_org_id == org_id,
        ).order_by(ReferralUse.created_at.desc()).limit(limit)
    )).scalars().all()
