"""职位 CRUD 服务层。"""

from __future__ import annotations

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_position import JobPosition, JobStatus
from app.schemas.job import JobCreate, JobUpdate


class JobService:
    """职位管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        status: str | None = None,
    ) -> tuple[list[JobPosition], int]:
        """分页查询职位列表"""
        query = select(JobPosition)
        count_query = select(func.count(JobPosition.id))

        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    JobPosition.title.ilike(pattern),
                    JobPosition.department.ilike(pattern),
                )
            )
            count_query = count_query.where(
                or_(
                    JobPosition.title.ilike(pattern),
                    JobPosition.department.ilike(pattern),
                )
            )
        if status:
            query = query.where(JobPosition.status == status)
            count_query = count_query.where(JobPosition.status == status)

        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(JobPosition.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_by_id(self, job_id: str) -> JobPosition | None:
        """根据ID获取职位"""
        import uuid
        try:
            uuid.UUID(job_id)
        except (ValueError, AttributeError):
            return None
        result = await self.db.execute(
            select(JobPosition).where(JobPosition.id == job_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: JobCreate) -> JobPosition:
        """创建职位"""
        job = JobPosition(**data.model_dump())
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def update(self, job_id: str, data: JobUpdate) -> JobPosition | None:
        """更新职位"""
        job = await self.get_by_id(job_id)
        if not job:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(job, key, value)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def delete(self, job_id: str) -> bool:
        """删除职位"""
        job = await self.get_by_id(job_id)
        if not job:
            return False
        await self.db.delete(job)
        await self.db.commit()
        return True
