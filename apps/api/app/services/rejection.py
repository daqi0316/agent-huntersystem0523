from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.candidate import Candidate, CandidateStatus
from app.models.candidate_state import RecruitmentCandidateState
from app.models.rejection import CandidateRejectionRecord, RejectionReason
from app.schemas.rejection import CandidateRejectRequest, RejectionReasonCreate


REJECTION_STAGE_TO_STATE: dict[str, RecruitmentCandidateState] = {
    "screening": RecruitmentCandidateState.SCREENING_REJECTED,
    "first_interview": RecruitmentCandidateState.FIRST_INTERVIEW_REJECTED,
    "second_interview": RecruitmentCandidateState.SECOND_INTERVIEW_REJECTED,
    "offer": RecruitmentCandidateState.OFFER_REJECTED,
}


class RejectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_reasons(
        self,
        skip: int = 0,
        limit: int = 50,
        category: str | None = None,
        is_active: bool | None = True,
    ) -> tuple[list[RejectionReason], int]:
        query = select(RejectionReason)
        count_query = select(func.count(RejectionReason.id))
        if category:
            query = query.where(RejectionReason.category == category)
            count_query = count_query.where(RejectionReason.category == category)
        if is_active is not None:
            query = query.where(RejectionReason.is_active == is_active)
            count_query = count_query.where(RejectionReason.is_active == is_active)
        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(RejectionReason.category.asc(), RejectionReason.code.asc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_reason_by_code(self, code: str) -> RejectionReason | None:
        result = await self.db.execute(select(RejectionReason).where(RejectionReason.code == code))
        return result.scalar_one_or_none()

    async def create_reason(self, data: RejectionReasonCreate) -> RejectionReason:
        reason = RejectionReason(**data.model_dump())
        self.db.add(reason)
        await self.db.commit()
        await self.db.refresh(reason)
        return reason

    async def list_candidate_records(
        self, candidate_id: str
    ) -> list[CandidateRejectionRecord]:
        result = await self.db.execute(
            select(CandidateRejectionRecord)
            .where(CandidateRejectionRecord.candidate_id == candidate_id)
            .order_by(CandidateRejectionRecord.created_at.desc())
        )
        return list(result.scalars().all())

    async def reject_candidate(
        self,
        candidate_id: str,
        data: CandidateRejectRequest,
        operator_id: str,
    ) -> CandidateRejectionRecord:
        candidate = await self._get_candidate(candidate_id)
        if candidate is None:
            raise LookupError("候选人不存在")
        reason = await self.get_reason_by_code(data.reason_code)
        if reason is None or not reason.is_active:
            raise ValueError("淘汰原因不存在或已停用")

        application = None
        if data.application_id:
            application = await self._get_application(data.application_id)
            if application is None:
                raise LookupError("申请不存在")
            if application.candidate_id != candidate_id:
                raise ValueError("申请不属于该候选人")

        record = CandidateRejectionRecord(
            candidate_id=candidate_id,
            application_id=data.application_id,
            job_profile_id=data.job_profile_id,
            reason_id=reason.id,
            reason_code=reason.code,
            reason_category=reason.category,
            primary_reason=reason.label,
            stage=data.stage,
            evidence=data.evidence,
            detail=data.detail,
            reusable_for_future=data.reusable_for_future,
            suggested_action=data.suggested_action,
            metadata_=data.metadata,
            operator_id=operator_id,
        )
        candidate.status = CandidateStatus.FAILED
        if data.stage in REJECTION_STAGE_TO_STATE:
            candidate.recruitment_state = REJECTION_STAGE_TO_STATE[data.stage]
        if application is not None:
            application.status = ApplicationStatus.REJECTED

        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def _get_candidate(self, candidate_id: str) -> Candidate | None:
        result = await self.db.execute(select(Candidate).where(Candidate.id == candidate_id))
        return result.scalar_one_or_none()

    async def _get_application(self, application_id: str) -> Application | None:
        result = await self.db.execute(select(Application).where(Application.id == application_id))
        return result.scalar_one_or_none()
