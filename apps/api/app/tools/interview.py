"""Interview tools — schedule, record feedback."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.interview import InterviewService

logger = logging.getLogger(__name__)


async def _handle_cancel_interview(interview_id: str = "", reason: str = "") -> dict[str, Any]:
    """取消已安排的面试。"""
    async with AsyncSessionLocal() as db:
        from app.services.interview import InterviewService
        svc = InterviewService(db)
        result = await svc.cancel(interview_id)
        if not result:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "面试不存在"}}
        return {"status": "success", "data": {"interview_id": interview_id, "status": "cancelled", "reason": reason}}


async def _handle_schedule_interview(candidate_id="", job_id="", scheduled_time="", notes=""):
    slot = {
        "type": "video",
        "scheduled_at": scheduled_time or datetime.now(timezone.utc).isoformat(),
        "notes": notes,
    }
    async with AsyncSessionLocal() as db:
        from app.services.interview import InterviewService
        svc = InterviewService(db)
        result = await svc.schedule(candidate_id, job_id, slot)
        if result is None:
            return {"id": None, "status": "failed", "error": {"code": "NOT_FOUND", "message": "候选人不存在"}}
        if result.get("error"):
            return result
        return {"id": result["id"], "status": "scheduled"}


async def _handle_record_feedback(interview_id="", score=0, evaluation=""):
    """v0.3 §7.1 / inventory §4.3 code smell 修：改走 InterviewService.save_evaluation()。

    之前直 db.add + db.commit，绕过 service 层的 RLS + 业务校验。
    现在所有 evaluation 写都集中到 service，未来加 RBAC / quota 一处改即可。
    """
    from app.services.interview import InterviewService

    if not interview_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "interview_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = InterviewService(db)
        try:
            ev = await svc.save_evaluation(
                interview_id=interview_id,
                overall_score=float(score) if score else None,
                feedback=evaluation or None,
            )
            return {
                "status": "success",
                "data": {
                    "id": ev.id,
                    "interview_id": ev.interview_id,
                    "score": ev.overall_score,
                },
            }
        except ValueError as e:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": str(e)}}


tools = [
    {"type": "function", "function": {"name": "schedule_interview", "description": "安排面试。创建一条面试记录，需要候选人、职位和面试时间。", "parameters": {"type": "object", "properties": {"candidate_id": {"type": "string", "description": "候选人 ID"}, "job_id": {"type": "string", "description": "职位 ID"}, "scheduled_time": {"type": "string", "description": "面试时间（ISO 格式）"}, "notes": {"type": "string", "description": "面试备注（可选）"}}, "required": ["candidate_id", "job_id", "scheduled_time"]}}},
    {"type": "function", "function": {"name": "record_feedback", "description": "记录面试反馈/评估结果。", "parameters": {"type": "object", "properties": {"interview_id": {"type": "string", "description": "面试 ID"}, "score": {"type": "integer", "description": "评分 1-10"}, "evaluation": {"type": "string", "description": "评价内容"}}, "required": ["interview_id"]}}},
    {"type": "function", "function": {"name": "cancel_interview", "description": "取消已安排的面试。", "parameters": {"type": "object", "properties": {"interview_id": {"type": "string", "description": "面试 ID"}, "reason": {"type": "string", "description": "取消原因（可选）"}}, "required": ["interview_id"]}}},
]

handlers = {
    "schedule_interview": _handle_schedule_interview,
    "record_feedback": _handle_record_feedback,
    "cancel_interview": _handle_cancel_interview,
}
