"""Schedule tool — 查询面试日程（支持过去和未来）。"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, and_, or_

from app.core.database import AsyncSessionLocal
from app.models.interview import Interview, InterviewStatus
from app.models.candidate import Candidate
from app.models.application import Application
from app.models.job_position import JobPosition


async def _handle_get_upcoming_interviews(
    days: int = 7,
    status_filter: str = "all",
    limit: int = 20,
) -> dict[str, Any]:
    """查询未来 n 天内的面试安排。"""
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        if status_filter == "all":
            statuses = [InterviewStatus.SCHEDULED, InterviewStatus.CONFIRMED]
        else:
            try:
                statuses = [InterviewStatus(status_filter)]
            except ValueError:
                statuses = [InterviewStatus.SCHEDULED, InterviewStatus.CONFIRMED]

        query = (
            select(Interview, Candidate.name.label("candidate_name"))
            .join(Candidate, Interview.candidate_id == Candidate.id)
            .where(
                and_(
                    Interview.scheduled_at >= now,
                    Interview.status.in_(statuses),
                )
            )
            .order_by(Interview.scheduled_at.asc())
            .limit(limit)
        )

        result = await db.execute(query)
        rows = result.all()

        interviews = []
        for row in rows:
            interview = row.Interview
            interviews.append({
                "id": interview.id,
                "candidate_id": interview.candidate_id,
                "candidate_name": row.candidate_name,
                "type": interview.type.value if interview.type else "video",
                "status": interview.status.value,
                "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else "",
                "duration_minutes": interview.duration_minutes or 60,
                "location": interview.location or "",
                "notes": interview.notes or "",
            })

        return {
            "total": len(interviews),
            "days": days,
            "status_filter": status_filter,
            "interviews": interviews,
        }


async def _handle_get_schedule(
    year: int | None = None,
    month: int | None = None,
    status_filter: str = "all",
    limit: int = 50,
) -> dict[str, Any]:
    """查询指定月份的面试日程（过去和未来都查）。

    Args:
        year: 年份（默认当前年）
        month: 月份 1-12（默认当前月）
        status_filter: 面试状态过滤，支持 scheduled/confirmed/completed/cancelled/all（默认 all）
        limit: 返回条数上限（默认 50）

    Returns:
        包含月份面试列表的字典，含统计摘要
    """
    now = datetime.now(timezone.utc)

    # Default to current month
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    # Build month range (UTC)
    _, last_day = monthrange(year, month)
    month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    async with AsyncSessionLocal() as db:
        # Build status filter
        if status_filter == "all":
            statuses = list(InterviewStatus)
        else:
            try:
                statuses = [InterviewStatus(status_filter)]
            except ValueError:
                statuses = list(InterviewStatus)

        # Query interviews in month range
        query = (
            select(
                Interview,
                Candidate.name.label("candidate_name"),
                JobPosition.title.label("job_title"),
            )
            .join(Candidate, Interview.candidate_id == Candidate.id)
            .outerjoin(Application, Interview.application_id == Application.id)
            .outerjoin(JobPosition, Application.job_id == JobPosition.id)
            .where(
                and_(
                    Interview.scheduled_at >= month_start,
                    Interview.scheduled_at <= month_end,
                    Interview.status.in_(statuses),
                )
            )
            .order_by(Interview.scheduled_at.asc())
            .limit(limit)
        )

        result = await db.execute(query)
        rows = result.all()

        interviews = []
        past_count = 0
        future_count = 0

        for row in rows:
            interview = row.Interview
            is_future = interview.scheduled_at and interview.scheduled_at > now
            if is_future:
                future_count += 1
            else:
                past_count += 1

            interviews.append({
                "id": interview.id,
                "candidate_id": interview.candidate_id,
                "candidate_name": row.candidate_name,
                "job_title": row.job_title or "未知职位",
                "type": interview.type.value if interview.type else "video",
                "status": interview.status.value,
                "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else "",
                "duration_minutes": interview.duration_minutes or 60,
                "location": interview.location or "",
                "notes": interview.notes or "",
            })

        return {
            "year": year,
            "month": month,
            "month_name": month_start.strftime("%Y年%m月"),
            "total": len(interviews),
            "past_count": past_count,
            "future_count": future_count,
            "status_filter": status_filter,
            "interviews": interviews,
        }


tools = [
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_interviews",
            "description": "查询未来 n 天内已安排的面试日程。返回候选人姓名、时间、地点等信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "向前查询的天数（默认 7 天）",
                        "default": 7,
                    },
                    "status_filter": {
                        "type": "string",
                        "description": "面试状态过滤：scheduled / confirmed / all（默认 all）",
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数上限（默认 20）",
                        "default": 20,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "查询指定月份的面试日程（过去和未来的都查）。可以回答「5月份有多少面试」「6月面试安排」等问题。返回该月所有面试记录，含候选人姓名、职位、时间、地点、状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "年份（默认今年）",
                    },
                    "month": {
                        "type": "integer",
                        "description": "月份 1-12（默认当月）",
                    },
                    "status_filter": {
                        "type": "string",
                        "description": "面试状态过滤：scheduled / confirmed / completed / cancelled / all（默认 all）",
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数上限（默认 50）",
                        "default": 50,
                    },
                },
            },
        },
    },
]

handlers = {
    "get_upcoming_interviews": _handle_get_upcoming_interviews,
    "get_schedule": _handle_get_schedule,
}
