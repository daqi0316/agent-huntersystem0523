"""AggregationService — 从 OperationLog 物化聚合到 operation_stats_hourly。

每 5 分钟运行一次，统计上一小时各 Agent 的操作指标。
避免前端 Dashboard 实时扫全表。
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func as sa_func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.operation_log import OperationLog, OperationStatus, ErrorCategory
from app.models.operation_stats import OperationStatsHourly

logger = logging.getLogger(__name__)

AGGREGATION_INTERVAL_MINUTES = 5


async def run_aggregation() -> int:
    """执行一次聚合：扫描 OperationLog → UPSERT operation_stats_hourly。"""
    now = datetime.now(timezone.utc)
    bucket_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    bucket_end = bucket_start + timedelta(hours=1)

    async with AsyncSessionLocal() as db:
        ops = await _fetch_ops_in_range(db, bucket_start, bucket_end)
        if not ops:
            return 0

        by_agent: dict[str, dict[str, Any]] = {}
        for op in ops:
            key = f"{op.agent_name}:{op.action or 'unknown'}"
            if key not in by_agent:
                by_agent[key] = {
                    "agent_name": op.agent_name,
                    "action": op.action or "",
                    "total": 0, "success": 0, "fail": 0,
                    "system_error": 0, "durations": [],
                }
            stat = by_agent[key]
            stat["total"] += 1
            if op.status == OperationStatus.COMPLETED:
                stat["success"] += 1
            elif op.status == OperationStatus.FAILED:
                stat["fail"] += 1
                if op.error_category == ErrorCategory.SYSTEM.value:
                    stat["system_error"] += 1
            if op.duration_ms is not None:
                stat["durations"].append(op.duration_ms)

        inserted = 0
        for stat in by_agent.values():
            durations = sorted(stat["durations"])
            avg = sum(durations) / len(durations) if durations else None
            p50 = _percentile(durations, 50) if durations else None
            p95 = _percentile(durations, 95) if durations else None

            avg = round(avg, 1) if avg else None
            p50 = round(p50, 1) if p50 else None
            p95 = round(p95, 1) if p95 else None

            stmt = select(OperationStatsHourly).where(
                OperationStatsHourly.bucket_hour == bucket_start,
                OperationStatsHourly.agent_name == stat["agent_name"],
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.total_ops = stat["total"]
                existing.success_count = stat["success"]
                existing.fail_count = stat["fail"]
                existing.system_error_count = stat["system_error"]
                existing.avg_duration_ms = avg
                existing.p50_duration_ms = p50
                existing.p95_duration_ms = p95
            else:
                row = OperationStatsHourly(
                    bucket_hour=bucket_start,
                    agent_name=stat["agent_name"],
                    action=stat["action"],
                    total_ops=stat["total"],
                    success_count=stat["success"],
                    fail_count=stat["fail"],
                    system_error_count=stat["system_error"],
                    avg_duration_ms=avg,
                    p50_duration_ms=p50,
                    p95_duration_ms=p95,
                )
                db.add(row)
            inserted += 1

        await db.commit()
        logger.info("Aggregated %d buckets for hour %s", inserted, bucket_start.isoformat())
        return inserted


async def _fetch_ops_in_range(
    db: AsyncSession, start: datetime, end: datetime,
) -> list[OperationLog]:
    stmt = (
        select(OperationLog)
        .where(
            OperationLog.created_at >= start,
            OperationLog.created_at < end,
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _percentile(sorted_vals: list[float], p: int) -> float:
    if not sorted_vals:
        return 0.0
    k = (p / 100.0) * (len(sorted_vals) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


async def aggregation_loop() -> None:
    """后台循环：每 5 分钟执行一次聚合。"""
    logger.info("Aggregation loop started (interval=%d min)", AGGREGATION_INTERVAL_MINUTES)
    while True:
        try:
            await run_aggregation()
        except Exception as e:
            logger.error("Aggregation failed: %s", e)
        import asyncio
        await asyncio.sleep(AGGREGATION_INTERVAL_MINUTES * 60)
