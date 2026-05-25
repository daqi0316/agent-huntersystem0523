"""面试 CRUD API — 安排、确认、取消、完成。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.common import ListResponse
from app.services.interview import InterviewService

router = APIRouter()


@router.get("", response_model=ListResponse)
async def list_interviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询面试列表"""
    service = InterviewService(db)
    items, total = await service.list_all(skip=skip, limit=limit, status=status)
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{interview_id}")
async def get_interview(interview_id: str, db: AsyncSession = Depends(get_db)):
    """获取面试详情"""
    service = InterviewService(db)
    interview = await service._get_by_id(interview_id)
    if not interview:
        raise HTTPException(404, detail="面试不存在")
    return service._to_dict(interview)


@router.post("", status_code=201)
async def create_interview(
    candidate_id: str = Query(..., description="候选人 ID"),
    job_id: str = Query(..., description="职位 ID"),
    application_id: str | None = Query(None),
    type: str = Query("video", description="面试类型: video/phone/onsite/technical"),
    scheduled_at: str | None = Query(None, description="ISO 8601 时间"),
    duration_minutes: int = Query(60, ge=15),
    location: str | None = Query(None),
    notes: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """安排面试，含 slot 冲突检测"""
    service = InterviewService(db)
    slot = {
        "application_id": application_id or "",
        "type": type,
        "scheduled_at": scheduled_at or "",
        "duration_minutes": duration_minutes,
        "location": location or "",
        "notes": notes or "",
    }
    result = await service.schedule(candidate_id, job_id, slot)
    if result is None:
        raise HTTPException(404, detail="候选人不存在")
    if result.get("error"):
        raise HTTPException(409, detail=result["message"])
    return result


@router.patch("/{interview_id}/confirm")
async def confirm_interview(interview_id: str, db: AsyncSession = Depends(get_db)):
    """确认面试"""
    service = InterviewService(db)
    result = await service.confirm(interview_id)
    if not result:
        raise HTTPException(404, detail="面试不存在")
    return result


@router.patch("/{interview_id}/cancel")
async def cancel_interview(interview_id: str, db: AsyncSession = Depends(get_db)):
    """取消面试"""
    service = InterviewService(db)
    result = await service.cancel(interview_id)
    if not result:
        raise HTTPException(404, detail="面试不存在")
    return result


@router.patch("/{interview_id}/complete")
async def complete_interview(
    interview_id: str,
    feedback: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """完成面试（附带反馈）"""
    service = InterviewService(db)
    result = await service.complete(interview_id, feedback or "")
    if not result:
        raise HTTPException(404, detail="面试不存在")
    return result
