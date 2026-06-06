"""Screening & candidate tools — search, get, screen, evaluate."""

from __future__ import annotations

import logging
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.candidate import CandidateService
from app.models.candidate import Candidate

logger = logging.getLogger(__name__)


async def _handle_search_candidates(query="", skill="", experience_min=0, limit=10):
    async with AsyncSessionLocal() as db:
        svc = CandidateService(db)
        items, total = await svc.list(limit=limit, search=query or None)
        return {
            "total": total,
            "candidates": [
                {
                    "id": c.id, "name": c.name,
                    "skills": c.skills or [], "experience_years": c.experience_years,
                    "current_company": c.current_company or "", "current_title": c.current_title or "",
                }
                for c in items
            ],
        }


async def _handle_get_candidate(candidate_id=""):
    async with AsyncSessionLocal() as db:
        svc = CandidateService(db)
        c = await svc.get_by_id(candidate_id)
        if not c:
            return {"error": "not_found"}
        return {
            "id": c.id, "name": c.name, "email": c.email,
            "phone": c.phone or "", "skills": c.skills or [],
            "experience_years": c.experience_years,
            "current_company": c.current_company or "",
            "current_title": c.current_title or "",
            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
        }


async def _handle_screen_resume(candidate_id="", job_id=""):
    from app.services.screening import ScreeningService
    svc = ScreeningService()
    return await svc.screen_resume(candidate_id=candidate_id, job_id=job_id)


async def _handle_list_jobs(status="", limit=10):
    from app.services.job import JobService
    async with AsyncSessionLocal() as db:
        svc = JobService(db)
        items, total = await svc.list(limit=limit, status=status or None)
        return {"total": total, "jobs": [{"id": j.id, "title": j.title, "status": j.status.value if hasattr(j.status, 'value') else str(j.status)} for j in items]}


async def _handle_get_evaluations(candidate_id="", limit=5):
    from sqlalchemy import select
    from app.models.interview_evaluation import InterviewEvaluation
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(InterviewEvaluation).where(InterviewEvaluation.candidate_id == candidate_id).limit(limit)
        )
        evals = list(result.scalars().all())
        return {"evaluations": [{"id": e.id, "score": e.overall_score, "verdict": e.verdict} for e in evals]}


tools = [
    {"type": "function", "function": {"name": "screen_resume", "description": "对候选人进行 AI 简历初筛，评估与某个职位的匹配度。", "parameters": {"type": "object", "properties": {"candidate_id": {"type": "string", "description": "候选人 ID"}, "job_id": {"type": "string", "description": "职位 ID"}}, "required": ["candidate_id", "job_id"]}}},
    {"type": "function", "function": {"name": "list_jobs", "description": "查看当前招聘中的职位列表。", "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["active", "closed", "draft"], "description": "按状态筛选"}, "limit": {"type": "integer", "description": "返回数量上限", "default": 10}}}}},
    {"type": "function", "function": {"name": "get_evaluations", "description": "查看候选人的评估报告。", "parameters": {"type": "object", "properties": {"candidate_id": {"type": "string", "description": "候选人 ID"}, "limit": {"type": "integer", "description": "返回数量上限", "default": 5}}}}},
]

# v0.3 §4.2 / inventory §4.2 重名合并：search_candidates / get_candidate 删
# 完整版（聚合 interviews + applications）见 candidate_search.py：
#   - candidate_search.search_candidates（含 skill / experience_min 过滤）
#   - candidate_search.get_candidate_detail（含 timeline + applications）

handlers = {
    "screen_resume": _handle_screen_resume,
    "list_jobs": _handle_list_jobs,
    "get_evaluations": _handle_get_evaluations,
}
