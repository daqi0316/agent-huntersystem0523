"""Interview tools — schedule, record feedback."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.interview import InterviewService

logger = logging.getLogger(__name__)


async def _handle_schedule_interview(candidate_id="", job_id="", scheduled_time="", notes=""):
    from app.schemas.candidate import InterviewCreate
    async with AsyncSessionLocal() as db:
        svc = InterviewService(db)
        data = InterviewCreate(
            candidate_id=candidate_id,
            job_id=job_id,
            scheduled_at=scheduled_time or datetime.now(timezone.utc).isoformat(),
            type="video",
            notes=notes,
        )
        interview = await svc.create(data)
        return {"id": interview.id, "status": "scheduled"}


async def _handle_record_feedback(interview_id="", score=0, evaluation=""):
    async with AsyncSessionLocal() as db:
        from app.models.interview_evaluation import InterviewEvaluation
        import uuid
        ev = InterviewEvaluation(
            id=str(uuid.uuid4()), interview_id=interview_id,
            overall_score=score, verdict="",
        )
        db.add(ev)
        await db.commit()
        return {"id": ev.id, "status": "recorded"}


tools = [
    {"type": "function", "function": {"name": "schedule_interview", "description": "安排面试。创建一条面试记录，需要候选人、职位和面试时间。", "parameters": {"type": "object", "properties": {"candidate_id": {"type": "string", "description": "候选人 ID"}, "job_id": {"type": "string", "description": "职位 ID"}, "scheduled_time": {"type": "string", "description": "面试时间（ISO 格式）"}, "notes": {"type": "string", "description": "面试备注（可选）"}}, "required": ["candidate_id", "job_id", "scheduled_time"]}}},
    {"type": "function", "function": {"name": "record_feedback", "description": "记录面试反馈/评估结果。", "parameters": {"type": "object", "properties": {"interview_id": {"type": "string", "description": "面试 ID"}, "score": {"type": "integer", "description": "评分 1-10"}, "evaluation": {"type": "string", "description": "评价内容"}}, "required": ["interview_id"]}}},
]

handlers = {
    "schedule_interview": _handle_schedule_interview,
    "record_feedback": _handle_record_feedback,
}
