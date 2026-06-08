from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_profile import JobProfile
from app.schemas.job_profile import JobProfileCreate, JobProfileUpdate


class JobProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        level: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[JobProfile], int]:
        query = select(JobProfile)
        count_query = select(func.count(JobProfile.id))

        if search:
            pattern = f"%{search}%"
            condition = or_(
                JobProfile.code.ilike(pattern),
                JobProfile.title.ilike(pattern),
                JobProfile.department.ilike(pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)
        if level:
            query = query.where(JobProfile.level == level)
            count_query = count_query.where(JobProfile.level == level)
        if is_active is not None:
            query = query.where(JobProfile.is_active == is_active)
            count_query = count_query.where(JobProfile.is_active == is_active)

        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(JobProfile.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_by_id(self, profile_id: str) -> JobProfile | None:
        import uuid
        try:
            uuid.UUID(profile_id)
        except (ValueError, AttributeError):
            return None
        result = await self.db.execute(select(JobProfile).where(JobProfile.id == profile_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> JobProfile | None:
        result = await self.db.execute(select(JobProfile).where(JobProfile.code == code))
        return result.scalar_one_or_none()

    async def create(self, data: JobProfileCreate) -> JobProfile:
        profile = JobProfile(**data.model_dump(mode="json"))
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def update(self, profile_id: str, data: JobProfileUpdate) -> JobProfile | None:
        profile = await self.get_by_id(profile_id)
        if profile is None:
            return None
        for key, value in data.model_dump(exclude_unset=True, mode="json").items():
            setattr(profile, key, value)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile
