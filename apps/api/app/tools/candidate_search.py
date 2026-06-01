"""Candidate search and detail tools."""

from __future__ import annotations

import logging
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.candidate import CandidateService
from app.agents.pii_filter import mask_pii

logger = logging.getLogger(__name__)


async def _handle_search_candidates(
    query: str = "",
    status: str = "",
    skills: list[str] | None = None,
    skip: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    """搜索候选人列表，支持关键词、状态、技能过滤。"""
    async with AsyncSessionLocal() as db:
        svc = CandidateService(db)
        items, total = await svc.list(skip=skip, limit=limit, search=query or None, status=status or None)

        results = []
        for c in items:
            results.append({
                "candidate_id": c.id,
                "name": mask_pii(c.name or ""),
                "email": mask_pii(c.email),
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "current_title": c.current_title or "",
                "current_company": c.current_company or "",
                "skills": c.skills or [],
                "experience_years": c.experience_years,
            })

        return {"total": total, "items": results, "skip": skip, "limit": limit}


async def _handle_get_candidate_detail(candidate_id: str = "") -> dict[str, Any]:
    """获取候选人完整详情，包含 timeline 事件。"""
    if not candidate_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "candidate_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = CandidateService(db)
        candidate = await svc.get_by_id(candidate_id)
        if not candidate:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "候选人不存在"}}

        from app.services.interview import InterviewService
        from app.services.application import ApplicationService

        interview_svc = InterviewService(db)
        app_svc = ApplicationService(db)

        interviews = await interview_svc.list_by_candidate(candidate_id)
        applications, _ = await app_svc.list(skip=0, limit=50, candidate_id=candidate_id)

        return {
            "status": "success",
            "data": {
                "candidate_id": candidate.id,
                "name": mask_pii(candidate.name or ""),
                "email": mask_pii(candidate.email),
                "phone": mask_pii(candidate.phone or ""),
                "status": candidate.status.value if hasattr(candidate.status, "value") else str(candidate.status),
                "summary": candidate.summary or "",
                "skills": candidate.skills or [],
                "experience_years": candidate.experience_years,
                "education": candidate.education or "",
                "current_company": candidate.current_company or "",
                "current_title": candidate.current_title or "",
                "interviews": interviews,
                "applications": [{"id": a["id"], "job_id": a["job_id"], "status": a["status"], "match_score": a.get("match_score")} for a in applications],
                "created_at": str(candidate.created_at) if candidate.created_at else None,
            },
        }


tools = [
    {
        "type": "function",
        "function": {
            "name": "search_candidates",
            "description": "搜索候选人列表。支持按关键词（姓名/邮箱/职位）、状态过滤，返回分页结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（匹配姓名/邮箱/职位）"},
                    "status": {"type": "string", "description": "按状态过滤 (active/evaluating/evaluated/in_interview/completed/failed/archived)"},
                    "skills": {"type": "array", "items": {"type": "string"}, "description": "按技能标签过滤"},
                    "skip": {"type": "integer", "description": "分页偏移", "default": 0},
                    "limit": {"type": "integer", "description": "每页数量", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_candidate_detail",
            "description": "获取候选人完整详情，包含面试记录和申请记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "候选人 ID"},
                },
                "required": ["candidate_id"],
            },
        },
    },
]

handlers = {
    "search_candidates": _handle_search_candidates,
    "get_candidate_detail": _handle_get_candidate_detail,
}
