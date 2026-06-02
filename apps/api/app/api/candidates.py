"""候选人 CRUD API + 生命周期时间线。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success, error
from app.schemas.candidate import CandidateCreate, CandidateRead, CandidateUpdate
from app.schemas.common import ListResponse
from app.services.candidate import CandidateService

router = APIRouter()


@router.get("", response_model=ListResponse[CandidateRead])
async def list_candidates(
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询候选人列表"""
    service = CandidateService(db)
    items, total = await service.list(skip=skip, limit=limit, search=search, status=status)
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{candidate_id}")
async def get_candidate(candidate_id: str, db: AsyncSession = Depends(get_db)):
    """获取候选人详情"""
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)
    return success(candidate)


@router.post("", status_code=201)
async def create_candidate(data: CandidateCreate, db: AsyncSession = Depends(get_db)):
    """创建候选人"""
    service = CandidateService(db)
    return success(await service.create(data))


@router.put("/{candidate_id}")
async def update_candidate(
    candidate_id: str, data: CandidateUpdate, db: AsyncSession = Depends(get_db)
):
    """更新候选人"""
    service = CandidateService(db)
    candidate = await service.update(candidate_id, data)
    if not candidate:
        return error("候选人不存在", status_code=404)
    return success(candidate)


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: str, db: AsyncSession = Depends(get_db)):
    """删除候选人"""
    service = CandidateService(db)
    ok = await service.delete(candidate_id)
    if not ok:
        return error("候选人不存在", status_code=404)
    return success({"message": "候选人已删除"})


@router.get("/{candidate_id}/timeline")
async def candidate_timeline(candidate_id: str, db: AsyncSession = Depends(get_db)):
    """获取候选人全生命周期时间线。"""
    from datetime import datetime as dt_mod

    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)

    events = []

    events.append({
        "type": "created",
        "title": "候选人入库",
        "description": f"候选人 {candidate.name} 被添加至系统",
        "timestamp": candidate.created_at.isoformat() if candidate.created_at else "",
        "status": "completed",
        "metadata": {"source": candidate.source if hasattr(candidate, 'source') else "manual"},
    })

    from app.models.application import Application
    app_result = await db.execute(
        select(Application).where(Application.candidate_id == candidate_id)
    )
    applications = list(app_result.scalars().all())
    for app in applications:
        from app.models.job_position import JobPosition
        job = None
        if app.job_id:
            job_result = await db.execute(select(JobPosition).where(JobPosition.id == app.job_id))
            job = job_result.scalar_one_or_none()
        events.append({
            "type": "application",
            "title": f"投递职位: {job.title if job else '未知'}",
            "description": f"状态: {app.status}",
            "timestamp": app.created_at.isoformat() if app.created_at else "",
            "status": "completed" if app.status in ("offered", "hired", "rejected") else "in_progress",
            "metadata": {"status": app.status, "job_id": app.job_id},
        })

    if hasattr(candidate, 'evaluations') and candidate.evaluations:
        for ev in candidate.evaluations:
            events.append({
                "type": "evaluation",
                "title": "AI 评估完成",
                "description": f"评分: {ev.overall_score}/100",
                "timestamp": ev.created_at.isoformat() if hasattr(ev, 'created_at') and ev.created_at else "",
                "status": "completed",
                "metadata": {"score": ev.overall_score},
            })

    from app.models.interview import Interview
    iv_result = await db.execute(
        select(Interview).where(Interview.candidate_id == candidate_id)
    )
    interviews = list(iv_result.scalars().all())
    for iv in interviews:
        events.append({
            "type": "interview",
            "title": f"{'面试安排' if iv.status == 'scheduled' else '面试完成'}",
            "description": f"类型: {iv.type}, 状态: {iv.status}",
            "timestamp": iv.scheduled_at.isoformat() if iv.scheduled_at else "",
            "status": "completed" if iv.status in ("completed", "cancelled") else "pending",
            "metadata": {"status": iv.status, "type": iv.type, "id": iv.id},
        })

    from app.models.interview_evaluation import InterviewEvaluation
    try:
        ev_result = await db.execute(
            select(InterviewEvaluation).where(InterviewEvaluation.interview_id.in_(
                [iv.id for iv in interviews]
            )) if interviews else select(InterviewEvaluation).where(False)
        )
        evaluations = list(ev_result.scalars().all())
    except Exception:
        evaluations = []
    for ev in evaluations:
        events.append({
            "type": "feedback",
            "title": "面试反馈提交",
            "description": f"总体评分: {ev.overall_score if hasattr(ev, 'overall_score') and ev.overall_score else 'N/A'}/10",
            "timestamp": ev.created_at.isoformat() if hasattr(ev, 'created_at') and ev.created_at else "",
            "status": "completed",
            "metadata": {"score": ev.overall_score if hasattr(ev, 'overall_score') else None},
        })

    events.sort(key=lambda e: e.get("timestamp", ""), reverse=False)

    return success({
        "candidate_id": candidate_id,
        "candidate_name": candidate.name,
        "events": events,
        "total": len(events),
    })
