"""Dashboard API — 数据看板聚合统计。

统一返回所有 KPI 指标、趋势数据、最近动态。
减少前端多次请求的开销。
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.core.response import success
from app.models.operation_stats import OperationStatsHourly

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats")
async def dashboard_stats(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """数据看板聚合统计 — 一次返回所有 KPI + 趋势 + 动态。"""
    total_candidates = await _count(db, "candidates")
    total_jobs = await _count(db, "job_positions")
    active_interviews = await _count_with_condition(db, "interviews", "status", "scheduled")
    monthly_onboards = await _count_this_month(db, "candidates", "hired")

    # 最近动态（最后 6 条按创建时间倒序）
    recent_activities = await _recent_activities(db)

    # 近 30 天趋势
    trend = await _candidate_trend(db, days=30)

    return success({
        "kpis": [
            {"label": "候选人总数", "value": total_candidates or 0, "key": "candidates"},
            {"label": "招聘职位", "value": total_jobs or 0, "key": "jobs"},
            {"label": "进行中面试", "value": active_interviews or 0, "key": "interviews"},
            {"label": "本月入职", "value": monthly_onboards or 0, "key": "onboards"},
        ],
        "trend": trend,
        "recent_activities": recent_activities,
    })


async def _count(db: AsyncSession, table: str) -> int:
    try:
        result = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
        return result.scalar() or 0
    except Exception:
        return 0


async def _count_with_condition(db: AsyncSession, table: str, column: str, value: str) -> int:
    try:
        result = await db.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {column} = :val"),
            {"val": value},
        )
        return result.scalar() or 0
    except Exception:
        return 0


async def _count_this_month(db: AsyncSession, table: str, status_value: str) -> int:
    try:
        now = datetime.now(timezone.utc)
        first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE status = :status AND created_at >= :first_day"
            ),
            {"status": status_value, "first_day": first_day},
        )
        return result.scalar() or 0
    except Exception:
        return 0


async def _recent_activities(db: AsyncSession, limit: int = 6) -> list[dict]:
    """拼合 candidates 和 jobs 的创建事件作为动态。"""
    activities = []
    try:
        rows = await db.execute(
            text(
                "SELECT 'candidate', name, created_at FROM candidates "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        )
        for row in rows:
            _, name, ts = row
            time_str = ts.strftime("%H:%M") if ts else "--:--"
            activities.append(
                {"time": time_str, "text": f"新增候选人 {name}", "type": "apply"}
            )
    except Exception:
        pass

    try:
        rows = await db.execute(
            text(
                "SELECT 'job', title, created_at FROM job_positions "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        )
        for row in rows:
            _, title, ts = row
            time_str = ts.strftime("%H:%M") if ts else "--:--"
            activities.append(
                {"time": time_str, "text": f"新增职位「{title}」", "type": "job"}
            )
    except Exception:
        pass

    # 按时间排序
    activities.sort(key=lambda a: a["time"], reverse=True)
    return activities[:limit]


async def _candidate_trend(db: AsyncSession, days: int = 30) -> list[dict]:
    """近 N 天候选人新增趋势。"""
    points = []
    now = datetime.now(timezone.utc)
    try:
        for i in range(days - 1, -1, -1):
            day = now - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            result = await db.execute(
                text(
                    "SELECT COUNT(*) FROM candidates "
                    "WHERE created_at >= :start AND created_at < :end"
                ),
                {"start": day_start, "end": day_end},
            )
            count = result.scalar() or 0

            # 每 2 天采一个点避免太密
            if i % 2 == 0:
                points.append({"date": day.strftime("%m-%d"), "count": count})
    except Exception:
        pass

    return points if points else [{"date": now.strftime("%m-%d"), "count": 0}]


@router.get("/operations/summary")
async def operation_summary(
    db: AsyncSession = Depends(get_db),
):
    """AI 操作成功率摘要 — 过去 24h 各 Agent 指标。"""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    from sqlalchemy import select as sa_select
    from sqlalchemy.exc import SQLAlchemyError

    stmt = (
        sa_select(OperationStatsHourly)
        .where(OperationStatsHourly.bucket_hour >= since)
        .order_by(OperationStatsHourly.bucket_hour.desc())
    )
    try:
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
    except SQLAlchemyError as e:
        if "does not exist" in str(e).lower():
            logger.warning("operation_stats_hourly 表缺失，返空聚合: %s", e)
            rows = []
        else:
            raise

    by_agent: dict[str, dict] = {}
    for r in rows:
        key = r.agent_name
        if key not in by_agent:
            by_agent[key] = {
                "agent_name": key,
                "total_ops": 0, "success_count": 0, "fail_count": 0,
                "system_error_count": 0, "durations": [],
            }
        s = by_agent[key]
        s["total_ops"] += r.total_ops
        s["success_count"] += r.success_count
        s["fail_count"] += r.fail_count
        s["system_error_count"] += r.system_error_count
        if r.avg_duration_ms:
            s["durations"].append(r.avg_duration_ms)

    agents = []
    for s in by_agent.values():
        success_rate = round(s["success_count"] / s["total_ops"] * 100, 1) if s["total_ops"] > 0 else 0
        avg_dur = round(sum(s["durations"]) / len(s["durations"]), 1) if s["durations"] else 0
        agents.append({
            "agent_name": s["agent_name"],
            "total_ops": s["total_ops"],
            "success_count": s["success_count"],
            "fail_count": s["fail_count"],
            "system_error_count": s["system_error_count"],
            "success_rate": success_rate,
            "avg_duration_ms": avg_dur,
        })

    total_ops = sum(a["total_ops"] for a in agents)
    total_success = sum(a["success_count"] for a in agents)
    overall_rate = round(total_success / total_ops * 100, 1) if total_ops > 0 else 0
    system_errors = sum(a["system_error_count"] for a in agents)

    return success({
        "overall": {
            "total_ops": total_ops,
            "success_rate": overall_rate,
            "system_errors": system_errors,
            "period_hours": 24,
        },
        "agents": agents,
    })


@router.get("/operations/trend")
async def operation_trend(
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
):
    """AI 操作趋势 — 逐小时成功/失败/耗时折线数据。"""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    from sqlalchemy import select as sa_select
    from sqlalchemy.exc import SQLAlchemyError

    stmt = (
        sa_select(OperationStatsHourly)
        .where(OperationStatsHourly.bucket_hour >= since)
        .order_by(OperationStatsHourly.bucket_hour.asc())
    )
    try:
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
    except SQLAlchemyError as e:
        if "does not exist" in str(e).lower():
            logger.warning("operation_stats_hourly 表缺失，返空趋势: %s", e)
            rows = []
        else:
            raise

    all_agents = list(set(r.agent_name for r in rows))
    buckets: dict[str, dict] = {}
    for r in rows:
        ts = r.bucket_hour.strftime("%H:00")
        if ts not in buckets:
            buckets[ts] = {"hour": ts}
        buckets[ts][f"{r.agent_name}_total"] = buckets[ts].get(f"{r.agent_name}_total", 0) + r.total_ops
        buckets[ts][f"{r.agent_name}_success"] = buckets[ts].get(f"{r.agent_name}_success", 0) + r.success_count
        buckets[ts][f"{r.agent_name}_fail"] = buckets[ts].get(f"{r.agent_name}_fail", 0) + r.fail_count
        if r.avg_duration_ms:
            prev = buckets[ts].get(f"{r.agent_name}_avg_dur", 0)
            count = buckets[ts].get(f"{r.agent_name}_dur_count", 0)
            buckets[ts][f"{r.agent_name}_avg_dur"] = (prev * count + r.avg_duration_ms) / (count + 1)
            buckets[ts][f"{r.agent_name}_dur_count"] = count + 1

    timeline = sorted(buckets.values(), key=lambda b: b["hour"])
    return success({
        "agents": all_agents,
        "timeline": timeline,
    })
