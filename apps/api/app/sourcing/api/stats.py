"""Sourcing 统计 API (P0-9)"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal

router = APIRouter(tags=["sourcing/stats"])


@router.get("")
async def get_sourcing_stats():
    from app.models.candidate import Candidate
    from app.sourcing.models.sourcing_task import SourcingTask

    async with AsyncSessionLocal() as db:
        total_tasks = (await db.execute(select(func.count(SourcingTask.id)))).scalar() or 0
        success_count = (
            await db.execute(
                select(func.count(SourcingTask.id)).where(SourcingTask.status == "completed")
            )
        ).scalar() or 0
        success_rate = success_count / total_tasks if total_tasks > 0 else 0
        total_candidates = (
            await db.execute(
                select(func.count(Candidate.id)).where(Candidate.sourcing_task_id.isnot(None))
            )
        ).scalar() or 0

    return {
        "success": True,
        "data": {
            "total_tasks": total_tasks,
            "success_rate": round(success_rate, 4),
            "total_candidates": total_candidates,
            "platform_stats": {},
            "daily_stats": [],
        },
    }


@router.get("/health")
async def get_sourcing_health():
    from app.sourcing.models.platform_config import PlatformConfig
    from app.sourcing.models.platform_account import PlatformAccount

    async with AsyncSessionLocal() as db:
        platforms = (await db.execute(select(PlatformConfig))).scalars().all()
        p_status = {p.name: p.health_status for p in platforms}
        accounts = (await db.execute(select(PlatformAccount))).scalars().all()
        a_count = len([a for a in accounts if a.is_active])

    return {
        "success": True,
        "data": {
            "platforms": p_status,
            "accounts": {"total": len(accounts), "active": a_count},
            "proxy_pool": {"premium": 0, "standard": 0, "mobile": 0},
            "queue_depth": 0,
        },
    }
