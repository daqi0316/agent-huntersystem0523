"""Candidate management tools — create, update, archive candidates."""

from __future__ import annotations

import logging
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.candidate import CandidateService
from app.schemas.candidate import CandidateCreate, CandidateUpdate
from app.agents.pii_filter import mask_pii

logger = logging.getLogger(__name__)


async def _handle_create_candidate(
    name: str = "",
    email: str = "",
    phone: str = "",
    summary: str = "",
    skills: list[str] | None = None,
    experience_years: int | None = None,
    education: str = "",
    current_company: str = "",
    current_title: str = "",
) -> dict[str, Any]:
    """创建新候选人。"""
    if not email:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "邮箱不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = CandidateService(db)
        try:
            create_data = CandidateCreate(
                name=name or email.split("@")[0],
                email=email,
                phone=phone or None,
                summary=summary or None,
                skills=skills or [],
                experience_years=experience_years,
                education=education or None,
                current_company=current_company or None,
                current_title=current_title or None,
            )
            candidate = await svc.create(create_data)
            return {
                "status": "success",
                "data": {
                    "candidate_id": candidate.id,
                    "name": mask_pii(candidate.name or ""),
                    "email": mask_pii(candidate.email),
                    "phone": mask_pii(candidate.phone or ""),
                    "current_company": candidate.current_company or "",
                    "current_title": candidate.current_title or "",
                    "status": candidate.status.value if hasattr(candidate.status, "value") else str(candidate.status),
                },
            }
        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                return {"status": "failed", "error": {"code": "DUPLICATE", "message": f"该邮箱已存在候选人: {email}"}}
            logger.error("create_candidate failed: %s", e)
            return {"status": "failed", "error": {"code": "CREATE_FAILED", "message": str(e)}}


async def _handle_update_candidate(
    candidate_id: str = "",
    name: str = "",
    email: str = "",
    phone: str = "",
    summary: str = "",
    skills: list[str] | None = None,
    experience_years: int | None = None,
    education: str = "",
    current_company: str = "",
    current_title: str = "",
    status: str = "",
) -> dict[str, Any]:
    """更新候选人信息。"""
    if not candidate_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "candidate_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = CandidateService(db)
        candidate = await svc.get_by_id(candidate_id)
        if not candidate:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "候选人不存在"}}

        update_data = CandidateUpdate(
            name=name or None,
            email=email or None,
            phone=phone or None,
            summary=summary or None,
            skills=skills,
            experience_years=experience_years,
            education=education or None,
            current_company=current_company or None,
            current_title=current_title or None,
            status=status or None,
        )
        updated = await svc.update(candidate_id, update_data)
        if not updated:
            return {"status": "failed", "error": {"code": "UPDATE_FAILED", "message": "更新失败"}}

        return {
            "status": "success",
            "data": {
                "candidate_id": updated.id,
                "name": mask_pii(updated.name or ""),
                "email": mask_pii(updated.email),
                "phone": mask_pii(updated.phone or ""),
                "current_company": updated.current_company or "",
                "current_title": updated.current_title or "",
                "status": updated.status.value if hasattr(updated.status, "value") else str(updated.status),
            },
        }


async def _handle_archive_candidate(candidate_id: str = "") -> dict[str, Any]:
    """归档候选人（软删除）。"""
    if not candidate_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "candidate_id 不能为空"}}

    from app.models.candidate import CandidateStatus
    async with AsyncSessionLocal() as db:
        svc = CandidateService(db)
        candidate = await svc.get_by_id(candidate_id)
        if not candidate:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "候选人不存在"}}

        updated = await svc.update(candidate_id, CandidateUpdate(status=CandidateStatus.ARCHIVED.value))
        if not updated:
            return {"status": "failed", "error": {"code": "ARCHIVE_FAILED", "message": "归档失败"}}

        return {"status": "success", "data": {"candidate_id": candidate_id, "status": "archived"}}


tools = [
    {
        "type": "function",
        "function": {
            "name": "create_candidate",
            "description": "创建新候选人档案。当用户提供候选人基本信息（姓名、邮箱、联系方式等）时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "候选人姓名"},
                    "email": {"type": "string", "description": "邮箱（唯一标识，不可为空）"},
                    "phone": {"type": "string", "description": "电话"},
                    "summary": {"type": "string", "description": "个人简介"},
                    "skills": {"type": "array", "items": {"type": "string"}, "description": "技能列表"},
                    "experience_years": {"type": "integer", "description": "工作年限"},
                    "education": {"type": "string", "description": "教育背景"},
                    "current_company": {"type": "string", "description": "当前公司"},
                    "current_title": {"type": "string", "description": "当前职位"},
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_candidate",
            "description": "更新候选人的基本信息、技能、工作经历等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "候选人 ID"},
                    "name": {"type": "string", "description": "姓名"},
                    "email": {"type": "string", "description": "邮箱"},
                    "phone": {"type": "string", "description": "电话"},
                    "summary": {"type": "string", "description": "个人简介"},
                    "skills": {"type": "array", "items": {"type": "string"}, "description": "技能列表"},
                    "experience_years": {"type": "integer", "description": "工作年限"},
                    "education": {"type": "string", "description": "教育背景"},
                    "current_company": {"type": "string", "description": "当前公司"},
                    "current_title": {"type": "string", "description": "当前职位"},
                    "status": {"type": "string", "description": "状态 (active/archived/blacklisted)"},
                },
                "required": ["candidate_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "archive_candidate",
            "description": "归档候选人（软删除），归档后候选人不在列表中出现但数据保留。",
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
    "create_candidate": _handle_create_candidate,
    "update_candidate": _handle_update_candidate,
    "archive_candidate": _handle_archive_candidate,
}
