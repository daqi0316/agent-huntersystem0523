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

    async def create(self, data: CandidateCreate, org_id: str | None = None) -> Candidate:
        """创建候选人 (org-scoped, 自动挂 org_id)。"""
        payload = data.model_dump()
        if org_id is not None:
            payload["org_id"] = org_id
        candidate = Candidate(**payload)
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

    # ── 初筛状态机 ──────────────────────────────────────────

    _ALLOWED_START_SCREENING = {
        CandidateStatus.ACTIVE,
        CandidateStatus.PENDING_EVAL,
    }
    _ALLOWED_SCREENING_FAILED = {
        CandidateStatus.EVALUATING,
        CandidateStatus.EVALUATED,
    }

    async def start_screening(self, candidate_id: str) -> Candidate | None:
        """开始初筛：状态机校验 → 更新为 evaluating。"""
        candidate = await self.get_by_id(candidate_id)
        if not candidate:
            return None
        if candidate.status not in self._ALLOWED_START_SCREENING:
            raise ValueError(
                f"候选人状态 '{candidate.status.value}' 不允许开始初筛 "
                f"(仅允许: {[s.value for s in self._ALLOWED_START_SCREENING]})"
            )
        candidate.status = CandidateStatus.EVALUATING
        await self.db.commit()
        await self.db.refresh(candidate)
        return candidate

    async def complete_screening(self, candidate_id: str, passed: bool) -> Candidate | None:
        """完成初筛：更新候选人状态为 evaluated / failed。"""
        candidate = await self.get_by_id(candidate_id)
        if not candidate:
            return None
        new_status = CandidateStatus.EVALUATED if passed else CandidateStatus.FAILED
        # 允许从 evaluating 直接完成，也允许从 evaluated 重试到 failed
        if candidate.status == CandidateStatus.EVALUATING or (
            not passed and candidate.status in self._ALLOWED_SCREENING_FAILED
        ):
            candidate.status = new_status
            await self.db.commit()
            await self.db.refresh(candidate)
        return candidate

    async def move_to_interview(self, candidate_id: str) -> Candidate | None:
        """进入面试阶段：状态机 eveluated/in_interview → in_interview。"""
        candidate = await self.get_by_id(candidate_id)
        if not candidate:
            return None
        if candidate.status not in (CandidateStatus.EVALUATED, CandidateStatus.IN_INTERVIEW):
            raise ValueError(
                f"候选人状态 '{candidate.status.value}' 不允许安排面试 "
                "(仅允许: evaluated, in_interview)"
            )
        candidate.status = CandidateStatus.IN_INTERVIEW
        await self.db.commit()
        await self.db.refresh(candidate)
        return candidate

    async def complete_interview(self, candidate_id: str) -> Candidate | None:
        """完成面试：状态机 in_interview → completed。"""
        candidate = await self.get_by_id(candidate_id)
        if not candidate:
            return None
        if candidate.status != CandidateStatus.IN_INTERVIEW:
            raise ValueError(
                f"候选人状态 '{candidate.status.value}' 不允许完成面试 "
                "(仅允许: in_interview)"
            )
        candidate.status = CandidateStatus.COMPLETED
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
