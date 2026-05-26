"""候选人 CRUD API。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success
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
        raise HTTPException(404, detail="候选人不存在")
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
        raise HTTPException(404, detail="候选人不存在")
    return success(candidate)


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: str, db: AsyncSession = Depends(get_db)):
    """删除候选人"""
    service = CandidateService(db)
    ok = await service.delete(candidate_id)
    if not ok:
        raise HTTPException(404, detail="候选人不存在")
    return success({"message": "候选人已删除"})
