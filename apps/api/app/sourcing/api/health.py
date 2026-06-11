"""P1-13: Sourcing 模块健康检查"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.sourcing.models.sourcing_task import SourcingTask

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sourcing/health", tags=["Sourcing"])


@router.get("")
async def sourcing_health(db: AsyncSession = Depends(get_db)):
    """健康检查：Redis / DB / 队列状态 / 平台状态"""
    status: dict[str, Any] = {"status": "ok", "services": {}}

    # DB 连通性
    try:
        await db.execute(select(func.now()))
        status["services"]["database"] = "ok"
    except Exception as e:
        status["services"]["database"] = f"error: {e}"
        status["status"] = "degraded"

    # Redis 连通性
    try:
        redis = await get_redis()
        await redis.ping()
        status["services"]["redis"] = "ok"
    except Exception as e:
        status["services"]["redis"] = f"error: {e}"
        status["status"] = "degraded"

    # 队列深度
    try:
        pending_count = (
            await db.execute(
                select(func.count(SourcingTask.id)).where(SourcingTask.status == "pending")
            )
        ).scalar() or 0
        running_count = (
            await db.execute(
                select(func.count(SourcingTask.id)).where(SourcingTask.status == "running")
            )
        ).scalar() or 0
        status["queue"] = {
            "pending": pending_count,
            "running": running_count,
        }
    except Exception as e:
        status["queue"] = {"error": str(e)}

    # 平台状态（扩展用 — P2+ 可汇报各平台账号活跃数）
    status["platforms"] = {"total": 0, "available": 0}

    return status
