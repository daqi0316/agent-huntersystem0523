from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.candidate import Candidate, CandidateStatus
from app.models.candidate_state import RecruitmentCandidateState
from app.models.rejection import (
    CandidateRejectionRecord,
    RejectionPreventableBy,
    RejectionReason,
    RejectionSource,
)
from app.models.scorecard import InterviewScorecardSubmission, ScorecardDimension
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
        stage_applicability = reason.stage_applicability or []
        if stage_applicability and data.stage not in stage_applicability:
            raise ValueError("淘汰原因不适用于当前阶段")

        application = None
        if data.application_id:
            application = await self._get_application(data.application_id)
            if application is None:
                raise LookupError("申请不存在")
            if application.candidate_id != candidate_id:
                raise ValueError("申请不属于该候选人")

        scorecard_submission = None
        if data.related_scorecard_submission_id:
            scorecard_submission = await self._get_scorecard_submission(data.related_scorecard_submission_id)
            if scorecard_submission is None:
                raise LookupError("评分卡提交不存在")
            if scorecard_submission.candidate_id != candidate_id:
                raise ValueError("评分卡提交不属于该候选人")
            if data.application_id and scorecard_submission.application_id != data.application_id:
                raise ValueError("评分卡提交不属于该申请")

        if data.related_dimension_id:
            dimension = await self._get_scorecard_dimension(data.related_dimension_id)
            if dimension is None:
                raise LookupError("评分维度不存在")
            if scorecard_submission is not None:
                await self._ensure_dimension_belongs_to_submission(
                    dimension.id,
                    scorecard_submission.scorecard_template_id,
                )

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
            source=RejectionSource(data.source),
            confidence=data.confidence,
            is_primary=data.is_primary,
            related_scorecard_submission_id=data.related_scorecard_submission_id,
            related_dimension_id=data.related_dimension_id,
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

    async def _get_scorecard_submission(self, submission_id: str) -> InterviewScorecardSubmission | None:
        result = await self.db.execute(
            select(InterviewScorecardSubmission).where(InterviewScorecardSubmission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def _get_scorecard_dimension(self, dimension_id: str) -> ScorecardDimension | None:
        result = await self.db.execute(select(ScorecardDimension).where(ScorecardDimension.id == dimension_id))
        return result.scalar_one_or_none()

    async def _ensure_dimension_belongs_to_submission(self, dimension_id: str, template_id: str) -> None:
        result = await self.db.execute(
            select(ScorecardDimension).where(
                ScorecardDimension.id == dimension_id,
                ScorecardDimension.scorecard_template_id == template_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise ValueError("评分维度不属于该评分卡模板")

    async def analytics(self) -> dict:
        records_result = await self.db.execute(select(CandidateRejectionRecord))
        records = list(records_result.scalars().all())
        reasons_result = await self.db.execute(select(RejectionReason))
        reasons = {item.code: item for item in reasons_result.scalars().all()}
        total = len(records)
        return {
            "total": total,
            "by_reason": self._distribution(
                [(record.reason_code, record.primary_reason) for record in records], total
            ),
            "by_stage": self._distribution([(record.stage, record.stage) for record in records], total),
            "by_job_profile": self._distribution(
                [
                    (
                        record.job_profile_id or "unassigned",
                        record.job_profile_id or "未关联岗位画像",
                    )
                    for record in records
                ],
                total,
            ),
            "by_preventable_by": self._distribution(
                [
                    (
                        self._preventable_value(reasons.get(record.reason_code)),
                        self._preventable_value(reasons.get(record.reason_code)),
                    )
                    for record in records
                ],
                total,
            ),
        }

    async def analytics_by_reason(self) -> dict:
        analytics = await self.analytics()
        return {"total": analytics["total"], "items": analytics["by_reason"]}

    async def analytics_by_stage(self) -> dict:
        analytics = await self.analytics()
        return {"total": analytics["total"], "items": analytics["by_stage"]}

    async def analytics_by_job_profile(self) -> dict:
        analytics = await self.analytics()
        return {"total": analytics["total"], "items": analytics["by_job_profile"]}

    async def analytics_preventable(self) -> dict:
        analytics = await self.analytics()
        return {
            "total": analytics["total"],
            "items": [
                {
                    **item,
                    "suggested_action": self._preventable_action(item["key"]),
                }
                for item in analytics["by_preventable_by"]
            ],
        }

    @staticmethod
    def _preventable_value(reason: RejectionReason | None) -> str:
        if reason is None:
            return RejectionPreventableBy.NONE.value
        return reason.preventable_by.value if hasattr(reason.preventable_by, "value") else str(reason.preventable_by)

    @staticmethod
    def _distribution(items: list[tuple[str, str]], total: int) -> list[dict]:
        counts: dict[str, dict] = {}
        for key, label in items:
            current = counts.setdefault(key, {"key": key, "label": label, "count": 0})
            current["count"] += 1
        return [
            {
                "key": item["key"],
                "label": item["label"],
                "count": item["count"],
                "percentage": round(item["count"] / total, 4) if total else 0,
            }
            for item in sorted(counts.values(), key=lambda value: value["count"], reverse=True)
        ]

    @staticmethod
    def _preventable_action(preventable_by: str) -> str:
        actions = {
            RejectionPreventableBy.SOURCING.value: "优化寻访关键词、渠道准入和候选人来源质量",
            RejectionPreventableBy.SCREENING.value: "前置硬性条件校验和简历初筛追问",
            RejectionPreventableBy.SCORECARD.value: "调整评分卡维度、行为锚定和面试追问题",
            RejectionPreventableBy.COMPENSATION.value: "提前校准薪酬预期、预算边界和谈判策略",
            RejectionPreventableBy.PROCESS.value: "优化跟进 SLA、候选人沟通节奏和流程透明度",
            RejectionPreventableBy.NONE.value: "作为不可预防样本沉淀，持续观察是否形成新模式",
        }
        return actions.get(preventable_by, "复盘对应环节并形成改进动作")
