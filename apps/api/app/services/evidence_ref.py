"""统一证据协议服务 — EvidenceRef CRUD。"""
from __future__ import annotations

import uuid

from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_ref import EvidenceRef
from app.schemas.evidence_ref import EvidenceRefCreate


class EvidenceRefService:
    """证据引用管理。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: EvidenceRefCreate) -> EvidenceRef:
        ref = EvidenceRef(
            id=str(uuid.uuid4()),
            candidate_id=data.candidate_id,
            application_id=data.application_id,
            source_type=data.source_type,
            source_id=data.source_id,
            quote=data.quote,
            normalized_claim=data.normalized_claim,
            confidence=data.confidence,
            created_by_type=data.created_by_type,
            created_by_id=data.created_by_id,
        )
        self.db.add(ref)
        await self.db.commit()
        await self.db.refresh(ref)
        return ref

    async def list(
        self,
        candidate_id: str | None = None,
        application_id: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[EvidenceRef], int]:
        query = select(EvidenceRef)
        count_query = select(sa_func.count(EvidenceRef.id))

        if candidate_id:
            query = query.where(EvidenceRef.candidate_id == candidate_id)
            count_query = count_query.where(EvidenceRef.candidate_id == candidate_id)
        if application_id:
            query = query.where(EvidenceRef.application_id == application_id)
            count_query = count_query.where(EvidenceRef.application_id == application_id)
        if source_type:
            query = query.where(EvidenceRef.source_type == source_type)
            count_query = count_query.where(EvidenceRef.source_type == source_type)

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(EvidenceRef.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get(self, ref_id: str) -> EvidenceRef | None:
        result = await self.db.execute(
            select(EvidenceRef).where(EvidenceRef.id == ref_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, ref_id: str) -> bool:
        ref = await self.get(ref_id)
        if ref is None:
            return False
        await self.db.delete(ref)
        await self.db.commit()
        return True

    async def delete_by_candidate(self, candidate_id: str) -> int:
        result = await self.db.execute(
            select(EvidenceRef).where(EvidenceRef.candidate_id == candidate_id)
        )
        refs = list(result.scalars().all())
        for r in refs:
            await self.db.delete(r)
        await self.db.commit()
        return len(refs)
