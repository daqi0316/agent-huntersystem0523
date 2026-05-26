"""Dashboard API — 数据看板聚合统计。

统一返回所有 KPI 指标、趋势数据、最近动态。
减少前端多次请求的开销。
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id

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

    return {
        "success": True,
        "kpis": [
            {"label": "候选人总数", "value": total_candidates or 0, "key": "candidates"},
            {"label": "招聘职位", "value": total_jobs or 0, "key": "jobs"},
            {"label": "进行中面试", "value": active_interviews or 0, "key": "interviews"},
            {"label": "本月入职", "value": monthly_onboards or 0, "key": "onboards"},
        ],
        "trend": trend,
        "recent_activities": recent_activities,
    }


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
