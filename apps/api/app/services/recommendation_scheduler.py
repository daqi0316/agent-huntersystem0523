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
    """执行一次全局推荐扫描: 对所有用户生成推荐。

    Phase A 推后 (1): 每个 user 失败时 ``await db.rollback()`` 重置 session,
    避免 background task 占着 abort 的 connection 致 uvicorn HTTP hang.
    根因推测见 docs/mcp-v4-fix-1-ship-report.md §3.1.
    """
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
                    await db.rollback()

            logger.info(
                "Recommendation scan complete: %d users scanned, %d recommendations generated",
                len(users), total,
            )
    except Exception as e:
        logger.error("Recommendation scan crashed: %s", e)


async def recommendation_scheduler_loop() -> None:
    """后台循环: 按间隔执行推荐扫描。

    A5+Fix-1: scan 失败时 sleep 5min (transient) 避免死循环疯狂重试饿死 uvicorn worker,
    导致 HTTP 请求 hang (curl 短连接幸运命中, httpx connection pool 死等)。
    """
    logger.info(
        "Recommendation scheduler started (interval=%d min)",
        RECOMMENDATION_SCAN_INTERVAL_MINUTES,
    )
    while True:
        try:
            await run_recommendation_scan()
        except Exception as e:
            logger.warning(
                "Recommendation scan failed (transient, retry in 5min): %s", e,
            )
            await asyncio.sleep(300)  # 5 分钟防疯狂重试
            continue

        await asyncio.sleep(RECOMMENDATION_SCAN_INTERVAL_MINUTES * 60)
