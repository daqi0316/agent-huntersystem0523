"""职位 CRUD API。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success, error
from app.schemas.job import JobCreate, JobRead, JobUpdate
from app.schemas.common import ListResponse
from app.services.job import JobService

router = APIRouter()


@router.get("", response_model=ListResponse[JobRead])
async def list_jobs(
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询职位列表"""
    service = JobService(db)
    items, total = await service.list(skip=skip, limit=limit, search=search, status=status)
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{job_id}")
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """获取职位详情"""
    service = JobService(db)
    job = await service.get_by_id(job_id)
    if not job:
        return error("职位不存在", status_code=404)
    return success(job)


@router.post("", status_code=201)
async def create_job(data: JobCreate, db: AsyncSession = Depends(get_db)):
    """创建职位"""
    service = JobService(db)
    return success(await service.create(data))


@router.put("/{job_id}")
async def update_job(job_id: str, data: JobUpdate, db: AsyncSession = Depends(get_db)):
    """更新职位"""
    service = JobService(db)
    job = await service.update(job_id, data)
    if not job:
        return error("职位不存在", status_code=404)
    return success(job)


@router.delete("/{job_id}")
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """删除职位"""
    service = JobService(db)
    ok = await service.delete(job_id)
    if not ok:
        return error("职位不存在", status_code=404)
    return success({"message": "职位已删除"})
