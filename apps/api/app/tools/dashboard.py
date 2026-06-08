"""Dashboard tools — stats, reports."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _handle_get_dashboard_stats():
    async with AsyncSessionLocal() as db:
        total_candidates = (await db.execute(text("SELECT COUNT(*) FROM candidates"))).scalar() or 0
        total_jobs = (await db.execute(text("SELECT COUNT(*) FROM job_positions"))).scalar() or 0
        active_interviews = (await db.execute(text("SELECT COUNT(*) FROM interviews WHERE status = 'SCHEDULED'"))).scalar() or 0
        return {
            "total_candidates": total_candidates,
            "total_jobs": total_jobs,
            "active_interviews": active_interviews,
            "period": "today",
        }


tools = [
    {"type": "function", "function": {"name": "get_dashboard_stats", "description": "获取招聘看板统计数据，包括候选人数量、职位数量、待初筛数量、面试安排数等。", "parameters": {"type": "object", "properties": {}}}},
]

handlers = {"get_dashboard_stats": _handle_get_dashboard_stats}
