"""Dataset item FastAPI 路由 — REST 接口。

Endpoints:
    POST   /api/v1/agentops/dataset/items          — 创建 dataset item
    GET    /api/v1/agentops/dataset/items           — 查询列表
    GET    /api/v1/agentops/dataset/items/{id}      — 查询单条
    DELETE /api/v1/agentops/dataset/items/{id}      — 删除
    GET    /api/v1/agentops/dataset/stats           — 统计
    POST   /api/v1/agentops/dataset/from-feedback/{feedback_id}  — 从反馈生成
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agentops.dataset.schemas import DatasetItemCreate, DatasetItemResponse, DatasetListResponse, DatasetStats
from app.agentops.dataset.service import DatasetService
from app.core.dependencies import get_current_user_id

router = APIRouter(prefix="/api/v1/agentops/dataset", tags=["agentops-dataset"])


def get_dataset_service() -> DatasetService:
    return DatasetService()


@router.post("/items", response_model=DatasetItemResponse, status_code=201)
async def create_item(
    req: DatasetItemCreate,
    service: DatasetService = Depends(get_dataset_service),
    user_id: str = Depends(get_current_user_id),
) -> DatasetItemResponse:
    """创建一条 dataset item。"""
    result = await service.create_item(req)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create dataset item")
    return result


@router.get("/items", response_model=DatasetListResponse)
async def list_items(
    category: str | None = Query(None),
    source: str | None = Query(None),
    trace_id: str | None = Query(None),
    session_id: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    feedback_id: str | None = Query(None),
    is_bad_case: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetListResponse:
    """查询 dataset item 列表，支持多条件过滤和分页。"""
    items, total = await service.list_items(
        category=category,
        source=source,
        trace_id=trace_id,
        session_id=session_id,
        entity_type=entity_type,
        entity_id=entity_id,
        feedback_id=feedback_id,
        is_bad_case=is_bad_case,
        limit=limit,
        offset=offset,
    )
    return DatasetListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/items/{item_id}", response_model=DatasetItemResponse)
async def get_item(
    item_id: str,
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetItemResponse:
    """按 ID 查询 dataset item。"""
    result = await service.get_item(item_id)
    if not result:
        raise HTTPException(status_code=404, detail="Dataset item not found")
    return result


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    service: DatasetService = Depends(get_dataset_service),
) -> None:
    """删除一条 dataset item。"""
    deleted = await service.delete_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset item not found")


@router.get("/stats", response_model=DatasetStats)
async def get_stats(
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetStats:
    """获取 dataset 统计信息。"""
    return await service.get_stats()


@router.post("/from-feedback/{feedback_id}", response_model=DatasetItemResponse, status_code=201)
async def create_from_feedback(
    feedback_id: str,
    service: DatasetService = Depends(get_dataset_service),
    user_id: str = Depends(get_current_user_id),
) -> DatasetItemResponse:
    """从一条反馈自动生成 dataset item（bad case 进入回归测试集）。"""
    result = await service.create_from_feedback(feedback_id)
    if not result:
        raise HTTPException(status_code=404, detail="Feedback not found or failed to create")
    return result
