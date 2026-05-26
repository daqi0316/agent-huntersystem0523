"""申请 CRUD API。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success
from app.schemas.application import ApplicationCreate, ApplicationRead, ApplicationUpdate
from app.schemas.common import ListResponse
from app.services.application import ApplicationService

router = APIRouter()


@router.get("", response_model=ListResponse)
async def list_applications(
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    status: str | None = None,
    candidate_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询申请列表"""
    service = ApplicationService(db)
    items, total = await service.list(
        skip=skip, limit=limit, search=search, status=status, candidate_id=candidate_id
    )
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{application_id}")
async def get_application(application_id: str, db: AsyncSession = Depends(get_db)):
    """获取申请详情"""
    service = ApplicationService(db)
    application = await service.get_by_id(application_id)
    if not application:
        raise HTTPException(404, detail="申请不存在")
    return success(application)


@router.post("", status_code=201)
async def create_application(data: ApplicationCreate, db: AsyncSession = Depends(get_db)):
    """创建申请"""
    service = ApplicationService(db)
    return success(await service.create(data))


@router.put("/{application_id}")
async def update_application(
    application_id: str, data: ApplicationUpdate, db: AsyncSession = Depends(get_db)
):
    """更新申请"""
    service = ApplicationService(db)
    application = await service.update(application_id, data)
    if not application:
        raise HTTPException(404, detail="申请不存在")
    return success(application)


@router.delete("/{application_id}")
async def delete_application(application_id: str, db: AsyncSession = Depends(get_db)):
    """删除申请"""
    service = ApplicationService(db)
    ok = await service.delete(application_id)
    if not ok:
        raise HTTPException(404, detail="申请不存在")
    return success({"message": "申请已删除"})
