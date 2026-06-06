"""P6-12: CSM churn 监控 API + cron 脚本 (csm-churn-monitor.py)。"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.csm import CSMTask, CSMTaskStatus
from app.services.csm import detect_churn_risks, mark_task_done

logger = logging.getLogger(__name__)

router = APIRouter()


class CSMTaskUpdate(BaseModel):
    status: CSMTaskStatus
    resolution_note: Optional[str] = None
    assigned_to: Optional[str] = None


@router.get("/csm/tasks")
async def get_csm_tasks(
    status: str = Query("open", description="open / in_progress / resolved / closed"),
    limit: int = Query(50, ge=1, le=200),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """CSM 团队看任务列表 (org-scoped)。"""
    org_ctx, db = ctx
    try:
        target_status = CSMTaskStatus(status)
    except ValueError:
        valid = ", ".join(s.value for s in CSMTaskStatus)
        raise HTTPException(400, f"invalid status: {status}. valid: {valid}")
    rows = (await db.execute(
        select(CSMTask)
        .where(CSMTask.org_id == org_ctx.org_id, CSMTask.status == target_status)
        .order_by(CSMTask.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return success([{
        "id": t.id,
        "org_id": t.org_id,
        "user_id": t.user_id,
        "task_type": t.task_type.value,
        "priority": t.priority.value,
        "status": t.status.value,
        "reason": t.reason,
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "assigned_to": t.assigned_to,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    } for t in rows])


@router.post("/csm/tasks/{task_id}/resolve")
async def resolve_task(
    task_id: str,
    body: CSMTaskUpdate,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    task = (await db.execute(
        select(CSMTask).where(CSMTask.id == task_id, CSMTask.org_id == org_ctx.org_id)
    )).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, "task not found")
    task.status = body.status
    if body.resolution_note:
        task.resolution_note = body.resolution_note
    if body.assigned_to:
        task.assigned_to = body.assigned_to
    from datetime import datetime
    task.updated_at = datetime.utcnow()
    await db.commit()
    return success({"id": task.id, "status": task.status.value})


@router.post("/csm/scan")
async def scan_churn_risks_now(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """admin: 立即跑一次检测 (无须等 cron)。"""
    org_ctx, db = ctx
    if org_ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "only admin/owner can trigger scan")
    tasks = await detect_churn_risks(db)
    return success({
        "new_tasks_count": len(tasks),
        "task_ids": [t.id for t in tasks],
    })
