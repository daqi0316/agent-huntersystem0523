"""Job management tools — create, update, close job positions."""

from __future__ import annotations

import logging
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.job import JobService
from app.schemas.job import JobCreate, JobUpdate
from app.models.job_position import JobStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _handle_create_job(
    title: str = "",
    department: str = "",
    location: str = "",
    description: str = "",
    requirements: str = "",
    salary_range: str = "",
    status: str = "active",
) -> dict[str, Any]:
    if not title:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "职位名称不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = JobService(db)
        try:
            create_data = JobCreate(
                title=title,
                department=department or None,
                location=location or None,
                description=description or None,
                requirements=requirements or None,
                salary_range=salary_range or None,
            )
            job = await svc.create(create_data)
            if status and status != "draft":
                await svc.update(job.id, JobUpdate(status=status))
                job = await svc.get_by_id(job.id)
            return {
                "status": "success",
                "data": {
                    "job_id": job.id,
                    "title": job.title,
                    "department": job.department or "",
                    "location": job.location or "",
                    "status": job.status.value if hasattr(job.status, "value") else str(job.status),
                },
            }
        except Exception as e:
            logger.error("create_job failed: %s", e)
            return {"status": "failed", "error": {"code": "CREATE_FAILED", "message": str(e)}}


async def _handle_update_job(
    job_id: str = "",
    title: str = "",
    department: str = "",
    location: str = "",
    description: str = "",
    requirements: str = "",
    salary_range: str = "",
    status: str = "",
) -> dict[str, Any]:
    if not job_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "job_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = JobService(db)
        job = await svc.get_by_id(job_id)
        if not job:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "职位不存在"}}

        update_data = JobUpdate(
            title=title or None,
            department=department or None,
            location=location or None,
            description=description or None,
            requirements=requirements or None,
            salary_range=salary_range or None,
            status=status or None,
        )
        updated = await svc.update(job_id, update_data)
        if not updated:
            return {"status": "failed", "error": {"code": "UPDATE_FAILED", "message": "更新失败"}}

        return {
            "status": "success",
            "data": {
                "job_id": updated.id,
                "title": updated.title,
                "department": updated.department or "",
                "location": updated.location or "",
                "status": updated.status.value if hasattr(updated.status, "value") else str(updated.status),
            },
        }


async def _handle_close_job(job_id: str = "") -> dict[str, Any]:
    if not job_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "job_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        svc = JobService(db)
        job = await svc.get_by_id(job_id)
        if not job:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "职位不存在"}}

        updated = await svc.update(job_id, JobUpdate(status=JobStatus.CLOSED.value))
        if not updated:
            return {"status": "failed", "error": {"code": "CLOSE_FAILED", "message": "关闭职位失败"}}

        return {"status": "success", "data": {"job_id": job_id, "status": "closed"}}


tools = [
    {
        "type": "function",
        "function": {
            "name": "create_job",
            "description": "创建新的招聘职位。当用户提供职位基本信息（名称、部门、地点等）时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "职位名称"},
                    "department": {"type": "string", "description": "所属部门"},
                    "location": {"type": "string", "description": "工作地点"},
                    "description": {"type": "string", "description": "职位描述"},
                    "requirements": {"type": "string", "description": "任职要求"},
                    "salary_range": {"type": "string", "description": "薪资范围（如 15k-25k）"},
                    "status": {"type": "string", "enum": ["draft", "active", "closed"], "description": "职位状态，默认 active"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_job",
            "description": "更新职位的信息（部门、地点、描述、要求、状态等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "职位 ID"},
                    "title": {"type": "string", "description": "职位名称"},
                    "department": {"type": "string", "description": "所属部门"},
                    "location": {"type": "string", "description": "工作地点"},
                    "description": {"type": "string", "description": "职位描述"},
                    "requirements": {"type": "string", "description": "任职要求"},
                    "salary_range": {"type": "string", "description": "薪资范围"},
                    "status": {"type": "string", "enum": ["draft", "active", "closed"], "description": "职位状态"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_job",
            "description": "关闭职位（招聘结束）。关闭后职位不再显示在招聘列表中。",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "职位 ID"},
                },
                "required": ["job_id"],
            },
        },
    },
]

handlers = {
    "create_job": _handle_create_job,
    "update_job": _handle_update_job,
    "close_job": _handle_close_job,
}
