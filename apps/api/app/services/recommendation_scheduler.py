"""主动推荐定时调度器 — 定期执行推荐扫描。

配置:
  - RECOMMENDATION_SCAN_INTERVAL_MINUTES: 扫描间隔（默认 60 分钟）
  - 在 lifespan 中通过 create_task 启动
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.recommendation_service import RecommendationService

logger = logging.getLogger(__name__)

RECOMMENDATION_SCAN_INTERVAL_MINUTES = 60


async def run_recommendation_scan() -> None:
    """执行一次全局推荐扫描: 对所有用户生成推荐。"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User))
            users = list(result.scalars().all())
            if not users:
                logger.info("No users found, skipping recommendation scan")
                return

            total = 0
            service = RecommendationService(db)
            for user in users:
                try:
                    recs = await service.generate_recommendations(user_id=user.id)
                    total += len(recs)
                except Exception as e:
                    logger.error("Recommendation scan failed for user %s: %s", user.id, e)

            logger.info(
                "Recommendation scan complete: %d users scanned, %d recommendations generated",
                len(users), total,
            )
    except Exception as e:
        logger.error("Recommendation scan crashed: %s", e)


async def recommendation_scheduler_loop() -> None:
    """后台循环: 按间隔执行推荐扫描。"""
    logger.info(
        "Recommendation scheduler started (interval=%d min)",
        RECOMMENDATION_SCAN_INTERVAL_MINUTES,
    )
    while True:
        try:
            await run_recommendation_scan()
        except Exception as e:
            logger.error("Recommendation scan failed: %s", e)

        await asyncio.sleep(RECOMMENDATION_SCAN_INTERVAL_MINUTES * 60)
