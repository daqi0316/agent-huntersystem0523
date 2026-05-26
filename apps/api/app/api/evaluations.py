"""评估列表 API — 从 candidates + applications 聚合评估数据。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.core.response import success
from app.schemas.common import ListResponse

router = APIRouter()


@router.get("", response_model=ListResponse)
async def list_evaluations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = None,
    status: str | None = None,
    candidate_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """评估记录列表 — 从申请记录聚合评估相关数据。

    聚合的评估字段包括:
    - overall_score: 来自 application.match_score
    - status: 来自 application.status
    - scores: 简化的维度分数列表
    - summary: 来自 application.ai_summary
    """
    query = select(Application).options(
        joinedload(Application.candidate),
        joinedload(Application.job),
    )
    count_query = select(func.count(Application.id))

    if search:
        pattern = f"%{search}%"
        query = query.where(
            Application.ai_summary.ilike(pattern)
            | Application.id.ilike(pattern)
        )
        count_query = count_query.where(
            Application.ai_summary.ilike(pattern)
            | Application.id.ilike(pattern)
        )
    if status:
        from app.models.application import ApplicationStatus

        try:
            st = ApplicationStatus(status)
            query = query.where(Application.status == st)
            count_query = count_query.where(Application.status == st)
        except ValueError:
            pass
    if candidate_id:
        query = query.where(Application.candidate_id == candidate_id)
        count_query = count_query.where(Application.candidate_id == candidate_id)

    total = (await db.execute(count_query)).scalar() or 0
    query = (
        query.order_by(Application.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    applications = result.scalars().all()

    items = []
    for app in applications:
        candidate = app.candidate
        items.append(
            {
                "id": app.candidate_id,
                "candidate_id": app.candidate_id,
                "job_id": app.job_id,
                "name": candidate.name if candidate else "",
                "job_title": app.job.title if app.job else "",
                "skills": candidate.skills if candidate else [],
                "status": app.status.value if hasattr(app.status, "value") else str(app.status),
                "overall_score": app.match_score or 0,
                "scores": _build_dimension_scores(app.match_score),
                "summary": app.ai_summary or "",
                "date": (
                    app.created_at.isoformat() if hasattr(app.created_at, "isoformat") else str(app.created_at)
                ),
            }
        )

    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{candidate_id}")
async def get_candidate_evaluation(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取单个候选人的评估汇总信息"""
    result = await db.execute(
        select(Application)
        .options(joinedload(Application.candidate))
        .where(Application.candidate_id == candidate_id)
        .order_by(Application.created_at.desc())
        .limit(1)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, detail="未找到该候选人的评估记录")

    candidate = app.candidate
    return success({
        "id": app.candidate_id,
        "candidate_id": app.candidate_id,
        "job_id": app.job_id,
        "name": candidate.name if candidate else "",
        "status": app.status.value if hasattr(app.status, "value") else str(app.status),
        "overall_score": app.match_score or 0,
        "scores": _build_dimension_scores(app.match_score),
        "summary": app.ai_summary or "",
        "date": (
            app.created_at.isoformat() if hasattr(app.created_at, "isoformat") else str(app.created_at)
        ),
    })


def _build_dimension_scores(match_score: float | None) -> list[dict]:
    """根据 match_score 构建模拟维度分数。

    实际生产线应使用真实的多维度评分数据。
    """
    base = match_score or 0
    return [
        {"name": "专业技能", "score": _clamp(base * 1.0)},
        {"name": "工作经验", "score": _clamp(base * 0.9)},
        {"name": "教育背景", "score": _clamp(base * 0.85)},
        {"name": "沟通能力", "score": _clamp(base * 0.8)},
        {"name": "团队协作", "score": _clamp(base * 0.85)},
    ]


def _clamp(value: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, round(value, 1)))
