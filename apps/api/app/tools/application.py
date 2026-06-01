"""Application tools — create, update status."""

from __future__ import annotations

import logging
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.application import ApplicationService
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.agents.pii_filter import mask_pii

logger = logging.getLogger(__name__)


async def _handle_create_application(
    candidate_id: str = "",
    job_id: str = "",
    resume_url: str = "",
) -> dict[str, Any]:
    """为候选人和职位创建一条申请记录。"""
    if not candidate_id or not job_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "candidate_id 和 job_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = ApplicationService(db)
        try:
            data = ApplicationCreate(candidate_id=candidate_id, job_id=job_id, resume_url=resume_url or None)
            app = await svc.create(data)
            return {
                "status": "success",
                "data": {
                    "application_id": app.id,
                    "candidate_id": app.candidate_id,
                    "job_id": app.job_id,
                    "status": app.status.value if hasattr(app.status, "value") else str(app.status),
                    "created_at": str(app.created_at),
                },
            }
        except Exception as e:
            logger.error("create_application failed: %s", e)
            return {"status": "failed", "error": {"code": "CREATE_FAILED", "message": str(e)}}


async def _handle_update_application_status(
    application_id: str = "",
    status: str = "",
    match_score: float | None = None,
    ai_summary: str = "",
) -> dict[str, Any]:
    """更新申请状态（进入面试/通过/拒绝/offer）。"""
    if not application_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "application_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = ApplicationService(db)
        existing = await svc.get_by_id(application_id)
        if not existing:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "申请不存在"}}

        update_data = ApplicationUpdate()
        if status:
            update_data.status = status
        if match_score is not None:
            update_data.match_score = match_score
        if ai_summary:
            update_data.ai_summary = ai_summary

        updated = await svc.update(application_id, update_data)
        if not updated:
            return {"status": "failed", "error": {"code": "UPDATE_FAILED", "message": "更新失败"}}

        return {
            "status": "success",
            "data": {
                "application_id": updated.id,
                "status": updated.status.value if hasattr(updated.status, "value") else str(updated.status),
                "match_score": updated.match_score,
            },
        }


tools = [
    {
        "type": "function",
        "function": {
            "name": "create_application",
            "description": "为候选人和职位创建申请记录。候选人需已存在。",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "候选人 ID"},
                    "job_id": {"type": "string", "description": "职位 ID"},
                    "resume_url": {"type": "string", "description": "简历 URL（可选）"},
                },
                "required": ["candidate_id", "job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_application_status",
            "description": "更新申请状态和评估结果。状态值: screening/passed/failed/interview/offer/accepted/rejected",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {"type": "string", "description": "申请 ID"},
                    "status": {"type": "string", "description": "新状态 (screening/passed/failed/interview/offer/accepted/rejected)"},
                    "match_score": {"type": "number", "description": "匹配分数 0-100"},
                    "ai_summary": {"type": "string", "description": "AI 评估摘要"},
                },
                "required": ["application_id"],
            },
        },
    },
]

handlers = {
    "create_application": _handle_create_application,
    "update_application_status": _handle_update_application_status,
}
