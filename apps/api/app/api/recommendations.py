"""Recommendations API — 主动推荐接口。

GET    /recommendations             — 获取推荐列表（分页，可选只看未读）
GET    /recommendations/unread-count — 未读推荐数量
POST   /recommendations/{id}/read   — 标记单条为已读
POST   /recommendations/read-all    — 标记全部为已读
POST   /recommendations/{id}/dismiss — 忽略推荐
POST   /recommendations/trigger     — 手动触发推荐扫描（用于测试/调试）
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.services.recommendation_service import RecommendationService

router = APIRouter()


class RecommendationOut(BaseModel):
    id: str
    type: str
    title: str
    description: str
    candidate_id: str | None = None
    job_id: str | None = None
    score: int | None = None
    reason: str | None = None
    read: bool
    created_at: str


class RecommendationListResponse(BaseModel):
    success: bool
    data: list[RecommendationOut]
    total: int


class UnreadCountResponse(BaseModel):
    success: bool
    count: int


class TriggerResponse(BaseModel):
    success: bool
    message: str
    count: int


@router.get("")
async def list_recommendations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取推荐列表。"""
    service = RecommendationService(db)
    recs = await service.list_recommendations(
        user_id=user_id, limit=limit, offset=offset, unread_only=unread_only,
    )
    return {
        "success": True,
        "data": [
            RecommendationOut(
                id=r.id,
                type=r.type.value,
                title=r.title,
                description=r.description,
                candidate_id=r.candidate_id,
                job_id=r.job_id,
                score=r.score,
                reason=r.reason,
                read=r.read,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in recs
        ],
        "total": len(recs),
    }


@router.get("/unread-count")
async def unread_count(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """未读推荐数量。"""
    service = RecommendationService(db)
    count = await service.count_unread(user_id)
    return {"success": True, "count": count}


@router.post("/{recommendation_id}/read")
async def mark_read(
    recommendation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """标记单条推荐为已读。"""
    service = RecommendationService(db)
    ok = await service.mark_read(recommendation_id, user_id)
    return {"success": ok, "data": {"id": recommendation_id, "read": True}}


@router.post("/read-all")
async def mark_all_read(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """标记所有推荐为已读。"""
    service = RecommendationService(db)
    count = await service.mark_all_read(user_id)
    return {"success": True, "data": {"updated_count": count}}


@router.post("/{recommendation_id}/dismiss")
async def dismiss_recommendation(
    recommendation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """忽略推荐。"""
    service = RecommendationService(db)
    ok = await service.dismiss(recommendation_id, user_id)
    return {"success": ok, "data": {"id": recommendation_id, "dismissed": True}}


@router.post("/trigger")
async def trigger_recommendations(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """手动触发推荐扫描（用于测试/调试）。"""
    service = RecommendationService(db)
    recs = await service.generate_recommendations(user_id)
    return {
        "success": True,
        "message": f"生成了 {len(recs)} 条推荐",
        "count": len(recs),
    }
