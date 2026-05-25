"""申请 CRUD 服务层。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.application import Application, ApplicationStatus
from app.models.candidate import Candidate
from app.models.job_position import JobPosition
from app.schemas.application import ApplicationCreate, ApplicationUpdate


class ApplicationService:
    """申请管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        status: str | None = None,
        candidate_id: str | None = None,
    ) -> tuple[list[dict], int]:
        """分页查询申请列表（含候选人姓名和职位名称）。"""
        query = (
            select(Application)
            .options(joinedload(Application.candidate), joinedload(Application.job))
        )
        count_query = select(func.count(Application.id))

        if search:
            pattern = f"%{search}%"
            query = query.where(Application.id.ilike(pattern))
            count_query = count_query.where(Application.id.ilike(pattern))
        if status:
            try:
                st = ApplicationStatus(status)
                query = query.where(Application.status == st)
                count_query = count_query.where(Application.status == st)
            except ValueError:
                pass
        if candidate_id:
            query = query.where(Application.candidate_id == candidate_id)
            count_query = count_query.where(Application.candidate_id == candidate_id)

        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(Application.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        applications = result.scalars().all()

        items = []
        for app in applications:
            d = {
                "id": app.id,
                "candidate_id": app.candidate_id,
                "job_id": app.job_id,
                "status": app.status.value if hasattr(app.status, "value") else app.status,
                "match_score": app.match_score,
                "ai_summary": app.ai_summary,
                "resume_url": app.resume_url,
                "candidate_name": app.candidate.name if app.candidate else "",
                "job_title": app.job.title if app.job else "",
                "created_at": app.created_at,
                "updated_at": app.updated_at,
            }
            items.append(d)

        return items, total

    async def get_by_id(self, application_id: str) -> Application | None:
        """根据 ID 获取申请。"""
        try:
            uuid.UUID(application_id)
        except (ValueError, AttributeError):
            return None
        result = await self.db.execute(
            select(Application)
            .options(joinedload(Application.candidate), joinedload(Application.job))
            .where(Application.id == application_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: ApplicationCreate) -> Application:
        """创建申请。"""
        application = Application(**data.model_dump())
        self.db.add(application)
        await self.db.commit()
        await self.db.refresh(application)
        return application

    async def update(
        self, application_id: str, data: ApplicationUpdate
    ) -> Application | None:
        """更新申请。"""
        application = await self.get_by_id(application_id)
        if not application:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            if key == "status" and value is not None:
                try:
                    value = ApplicationStatus(value)
                except ValueError:
                    continue
            setattr(application, key, value)
        await self.db.commit()
        await self.db.refresh(application)
        return application

    async def delete(self, application_id: str) -> bool:
        """删除申请。"""
        application = await self.get_by_id(application_id)
        if not application:
            return False
        await self.db.delete(application)
        await self.db.commit()
        return True
