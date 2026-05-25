"""候选人 CRUD 服务层。"""

from __future__ import annotations

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate, CandidateStatus
from app.schemas.candidate import CandidateCreate, CandidateUpdate


class CandidateService:
    """候选人管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Candidate], int]:
        """分页查询候选人列表"""
        query = select(Candidate)
        count_query = select(func.count(Candidate.id))

        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    Candidate.name.ilike(pattern),
                    Candidate.email.ilike(pattern),
                    Candidate.current_title.ilike(pattern),
                )
            )
            count_query = count_query.where(
                or_(
                    Candidate.name.ilike(pattern),
                    Candidate.email.ilike(pattern),
                    Candidate.current_title.ilike(pattern),
                )
            )
        if status:
            query = query.where(Candidate.status == status)
            count_query = count_query.where(Candidate.status == status)

        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(Candidate.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_by_id(self, candidate_id: str) -> Candidate | None:
        """根据ID获取候选人"""
        import uuid
        try:
            uuid.UUID(candidate_id)
        except (ValueError, AttributeError):
            return None
        result = await self.db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: CandidateCreate) -> Candidate:
        """创建候选人"""
        candidate = Candidate(**data.model_dump())
        self.db.add(candidate)
        await self.db.commit()
        await self.db.refresh(candidate)
        return candidate

    async def update(self, candidate_id: str, data: CandidateUpdate) -> Candidate | None:
        """更新候选人"""
        candidate = await self.get_by_id(candidate_id)
        if not candidate:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(candidate, key, value)
        await self.db.commit()
        await self.db.refresh(candidate)
        return candidate

    async def delete(self, candidate_id: str) -> bool:
        """删除候选人"""
        candidate = await self.get_by_id(candidate_id)
        if not candidate:
            return False
        await self.db.delete(candidate)
        await self.db.commit()
        return True
