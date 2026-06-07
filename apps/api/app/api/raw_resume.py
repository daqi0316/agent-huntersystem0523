"""v0.6a: raw_resume async API — submit + poll.

POST /raw-resumes/parse:   submit (enqueue RQ task, 返 raw_resume_id + task_id)
GET  /raw-resumes/{id}/status: poll (读 raw_resumes 表 status)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_current_user_id
from app.core.database import AsyncSessionLocal
from app.models.raw_resume import RawResume, RawResumeStatus, new_raw_resume_id
from app.services.parse_task import enqueue_parse_task, poll_parse_task

logger = logging.getLogger(__name__)

router = APIRouter()


class ParseSubmitRequest(BaseModel):
    content: str = ""
    file_url: str = ""
    file_type: str = ""
    filename: str = ""
    target_job_id: str = ""
    auto_create: bool = True


class ParseSubmitResponse(BaseModel):
    raw_resume_id: str
    task_id: str
    status: str = "processing"


@router.post("/parse", response_model=ParseSubmitResponse)
async def submit_parse(
    req: ParseSubmitRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Submit a parse task. Returns raw_resume_id + RQ task_id immediately.

    流程:
      1. 落 raw_resumes (status=processing, raw_text 完整保存)
      2. enqueue RQ task (worker 调 _do_extract_and_link 跑 LLM + 状态机更新)
      3. 立刻返 task_id (不等 LLM)
    """
    if not req.content and not req.file_url:
        raise HTTPException(status_code=400, detail="content or file_url required")

    content = req.content

    raw_resume_id = new_raw_resume_id()
    async with AsyncSessionLocal() as db:
        rr = RawResume(
            id=raw_resume_id,
            raw_text=content,
            file_url=req.file_url or None,
            file_type=req.file_type or None,
            filename=req.filename or None,
            target_job_id=req.target_job_id or None,
            status=RawResumeStatus.PROCESSING,
        )
        db.add(rr)
        await db.commit()

    try:
        task_id = enqueue_parse_task(
            raw_resume_id=raw_resume_id,
            content=content,
            auto_create=req.auto_create,
        )
    except Exception as e:
        logger.error("Failed to enqueue parse task for %s: %s", raw_resume_id, e)
        async with AsyncSessionLocal() as db:
            stuck = await db.get(RawResume, raw_resume_id)
            if stuck is not None:
                stuck.status = RawResumeStatus.FAILED
                stuck.error_message = f"enqueue_failed: {e}"
                await db.commit()
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {e}")

    return ParseSubmitResponse(
        raw_resume_id=raw_resume_id,
        task_id=task_id,
        status="processing",
    )


@router.get("/{raw_resume_id}/status")
async def get_status(
    raw_resume_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Poll task status by raw_resume_id.

    优先读 raw_resumes.status（_do_extract_and_link 写回, source of truth）。
    """
    result = await poll_parse_task(raw_resume_id)
    if result is None:
        raise HTTPException(status_code=404, detail="raw_resume not found")
    return result
