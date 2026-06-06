"""P6-12: CSM churn 监控 API + cron 脚本 (csm-churn-monitor.py)。"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.response import success
from app.models.csm import CSMTask, CSMTaskStatus
from app.services.csm import detect_churn_risks, list_pending_csm_tasks, mark_task_done

router = APIRouter()


class CSMTaskUpdate(BaseModel):
    status: str
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


@router.get("/csm/tasks")
async def get_csm_tasks(
    status_filter: Optional[str] = Query("pending", alias="status"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(AsyncSessionLocal),
):
    """CSM 团队看任务列表。"""
    from app.models.csm import CSMTaskStatus
    try:
        target_status = CSMTaskStatus(status_filter)
    except ValueError:
        raise HTTPException(400, f"invalid status: {status_filter}")
    tasks = (await db.execute(
        __import__("sqlalchemy").select(CSMTask).where(
            CSMTask.status == target_status,
        ).order_by(CSMTask.severity.asc(), CSMTask.created_at.asc()).limit(limit)
    )).scalars().all()
    return success([
        {
            "id": t.id,
            "org_id": t.org_id,
            "type": t.type.value,
            "severity": t.severity.value,
            "status": t.status.value,
            "title": t.title,
            "description": t.description,
            "metrics": t.metrics,
            "assigned_to": t.assigned_to,
            "due_at": t.due_at.isoformat() if t.due_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ])


@router.post("/csm/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    body: CSMTaskUpdate,
    db: AsyncSession = Depends(AsyncSessionLocal),
):
    task = await mark_task_done(db, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    return success({"id": task.id, "status": task.status.value, "completed_at": task.completed_at.isoformat()})


@router.post("/csm/scan")
async def scan_churn_risks_now(
    db: AsyncSession = Depends(AsyncSessionLocal),
):
    """admin: 立即跑一次检测 (无须等 cron)。"""
    tasks = await detect_churn_risks(db)
    return success({
        "new_tasks_count": len(tasks),
        "task_types": [t.type.value for t in tasks],
    })
