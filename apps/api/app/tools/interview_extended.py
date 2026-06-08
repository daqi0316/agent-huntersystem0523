"""Extended interview tools — reschedule, complete, get detail."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.interview import InterviewService
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _handle_reschedule_interview(
    interview_id: str = "",
    new_time: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """修改已安排面试的时间。v0.3 §7.1 / inventory §4.3 code smell 修：改走 InterviewService.reschedule()。"""
    if not interview_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "interview_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = InterviewService(db)
        result, err_code = await svc.reschedule(interview_id, new_time=new_time, reason=reason)
        if err_code == "NOT_FOUND":
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "面试不存在"}}
        if err_code == "INVALID_TIME":
            return {"status": "failed", "error": {"code": "INVALID_TIME", "message": "时间格式无效，请使用 ISO 8601 格式"}}
        return {
            "status": "success",
            "data": {
                "interview_id": result["id"] if result else interview_id,
                "scheduled_at": result.get("scheduled_at") if result else None,
                "status": result.get("status") if result else None,
            },
        }


async def _handle_complete_interview(
    interview_id: str = "",
    feedback: str = "",
) -> dict[str, Any]:
    """标记面试完成，附上面试反馈。"""
    if not interview_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "interview_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = InterviewService(db)
        result = await svc.complete(interview_id, feedback=feedback)
        if not result:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "面试不存在"}}
        return {"status": "success", "data": result}


async def _handle_get_interview_detail(interview_id: str = "") -> dict[str, Any]:
    """获取面试完整详情。"""
    if not interview_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "interview_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = InterviewService(db)
        interview = await svc._get_by_id(interview_id)
        if not interview:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "面试不存在"}}

        d = svc._to_dict(interview)
        return {"status": "success", "data": d}


tools = [
    {
        "type": "function",
        "function": {
            "name": "reschedule_interview",
            "description": "修改已安排面试的时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_id": {"type": "string", "description": "面试 ID"},
                    "new_time": {"type": "string", "description": "新面试时间（ISO 8601 格式）"},
                    "reason": {"type": "string", "description": "改期原因（可选）"},
                },
                "required": ["interview_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_interview",
            "description": "标记面试已完成，附上面试反馈。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_id": {"type": "string", "description": "面试 ID"},
                    "feedback": {"type": "string", "description": "面试反馈/备注"},
                },
                "required": ["interview_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_interview_detail",
            "description": "获取面试的完整详细信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_id": {"type": "string", "description": "面试 ID"},
                },
                "required": ["interview_id"],
            },
        },
    },
]

handlers = {
    "reschedule_interview": _handle_reschedule_interview,
    "complete_interview": _handle_complete_interview,
    "get_interview_detail": _handle_get_interview_detail,
}
