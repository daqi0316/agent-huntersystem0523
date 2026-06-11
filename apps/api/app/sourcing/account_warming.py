"""P3-2: 账号预热脚本 — 新注册账号逐步增加采集频率"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.sourcing.models.platform_account import PlatformAccount, AccountStatus
from app.sourcing.models.platform_config import PlatformConfig

logger = logging.getLogger(__name__)

WARMING_DAYS = 7
WARMING_QUOTA_STEPS = [10, 20, 40, 80, 150, 250, 300]


async def run_account_warming(db: AsyncSession, redis) -> dict[str, Any]:

    # 获取注册不超过 WARMING_DAYS 天的账号
    cutoff = datetime.now(timezone.utc) - timedelta(days=WARMING_DAYS)
    result = await db.execute(
        select(PlatformAccount).where(
            and_(
                PlatformAccount.created_at >= cutoff,
                PlatformAccount.account_type == "primary",
            )
        )
    )
    accounts = list(result.scalars().all())
    if not accounts:
        logger.debug("No accounts in warming period")
        return {"warmed": 0, "adjusted": 0}

    warmed = 0
    adjusted = 0
    for acct in accounts:
        age_days = (datetime.now(timezone.utc) - acct.created_at).days
        expected_quota = WARMING_QUOTA_STEPS[min(age_days, len(WARMING_QUOTA_STEPS) - 1)]

        result = await db.execute(
            select(PlatformConfig.daily_quota_per_account)
            .where(PlatformConfig.name == acct.platform)
        )
        default_quota = result.scalar_one_or_none() or 300

        if acct.daily_quota != expected_quota and expected_quota <= default_quota:
            logger.info(
                "Warming account %s (day %d/%d): quota %d → %d",
                acct.id, age_days + 1, WARMING_DAYS, acct.daily_quota, expected_quota,
            )
            acct.daily_quota = expected_quota
            adjusted += 1
            if acct.status == AccountStatus.LIMITED.value:
                acct.status = AccountStatus.ACTIVE.value
                warmed += 1

    if adjusted:
        await db.commit()
    return {"warmed": warmed, "adjusted": adjusted, "total_accounts": len(accounts)}
