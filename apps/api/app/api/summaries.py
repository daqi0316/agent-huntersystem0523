"""Cross-session memory summaries API — CRUD + FTS / hybrid search.

Uses SummaryService for PG + Qdrant operations.
All endpoints require authentication and scope to current user.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.core.qdrant import get_qdrant
from app.core.config import settings
from app.core.response import success, ok_list, ok_or_404, error
from app.llm import get_llm_client
from app.services.qdrant_service import QdrantService
from app.services.summary_service import (
    SummaryService,
    SEARCH_MODE_VECTOR,
    SEARCH_MODE_FTS,
    SEARCH_MODE_HYBRID,
)

router = APIRouter()


class SummaryUpdateRequest(BaseModel):
    summary: str = Field(..., min_length=1, max_length=3000, description="更新后的摘要文本")


@router.get("")
async def list_summaries(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """列出当前用户的所有跨会话记忆摘要（分页）。"""
    qdrant_client = await get_qdrant()
    qdrant_svc = QdrantService(client=qdrant_client, collection=settings.qdrant_memory_collection)
    svc = SummaryService(db=db, llm=get_llm_client(), qdrant=qdrant_svc)
    items, total = await svc.list_by_user(user_id, skip=skip, limit=limit)
    return ok_list(items, total, skip=skip, limit=limit)


@router.get("/search")
async def search_summaries(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    q: str = Query(..., min_length=1, description="搜索关键词"),
    mode: str = Query(
        SEARCH_MODE_FTS,
        pattern=f"^({SEARCH_MODE_VECTOR}|{SEARCH_MODE_FTS}|{SEARCH_MODE_HYBRID})$",
        description=f"搜索模式: {SEARCH_MODE_VECTOR}=向量, {SEARCH_MODE_FTS}=全文索引, {SEARCH_MODE_HYBRID}=混合",
    ),
    top_k: int = Query(10, ge=1, le=50, description="返回数量"),
):
    """搜索跨会话记忆摘要（FTS / 向量 / 混合模式）。

    - ``mode=fts``: PostgreSQL 全文索引搜索（关键词匹配）。
    - ``mode=vector``: Qdrant 向量相似度搜索（语义匹配）。
    - ``mode=hybrid``: 向量 + FTS 加权合并结果。
    """
    qdrant_client = await get_qdrant()
    qdrant_svc = QdrantService(client=qdrant_client, collection=settings.qdrant_memory_collection)
    svc = SummaryService(db=db, llm=get_llm_client(), qdrant=qdrant_svc)
    results = await svc.get_relevant(user_id, q, top_k=top_k, mode=mode)
    return ok_list(results, len(results))


@router.put("/{summary_id}")
async def update_summary(
    summary_id: str,
    data: SummaryUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """更新记忆摘要（PG + Qdrant re-embed）。"""
    qdrant_client = await get_qdrant()
    qdrant_svc = QdrantService(client=qdrant_client, collection=settings.qdrant_memory_collection)
    svc = SummaryService(db=db, llm=get_llm_client(), qdrant=qdrant_svc)
    ok = await svc.update_summary(summary_id, data.summary, user_id)
    if not ok:
        return error("记忆摘要不存在", status_code=404)
    return success({"id": summary_id, "summary": data.summary})


@router.delete("/{summary_id}")
async def delete_summary(
    summary_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除记忆摘要（PG + Qdrant）。"""
    qdrant_client = await get_qdrant()
    qdrant_svc = QdrantService(client=qdrant_client, collection=settings.qdrant_memory_collection)
    svc = SummaryService(db=db, llm=get_llm_client(), qdrant=qdrant_svc)
    ok = await svc.delete_summary(summary_id, user_id)
    if not ok:
        return error("记忆摘要不存在", status_code=404)
    return success({"id": summary_id, "deleted": True})
