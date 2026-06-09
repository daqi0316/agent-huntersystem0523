from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview_evaluation import EvaluationVerdict, InterviewRound
from app.models.job_profile import JobProfile, JobProfileVersion, JobProfileVersionStatus
from app.models.scorecard import (
    InterviewScorecardDimensionScore,
    InterviewScorecardSubmission,
    ScorecardBehaviorAnchor,
    ScorecardDimension,
    ScorecardRoundType,
    ScorecardStatus,
    ScorecardTemplate,
    ScorecardVerdict,
)
from app.schemas.scorecard import InterviewScorecardSubmissionCreate, ScorecardTemplateCreate
from app.services.interview import InterviewService


class ScorecardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_templates(
        self,
        skip: int = 0,
        limit: int = 20,
        job_profile_id: str | None = None,
        round_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        from sqlalchemy import func

        query = select(ScorecardTemplate)
        count_query = select(func.count(ScorecardTemplate.id))
        if job_profile_id:
            query = query.where(ScorecardTemplate.job_profile_id == job_profile_id)
            count_query = count_query.where(ScorecardTemplate.job_profile_id == job_profile_id)
        if round_type:
            query = query.where(ScorecardTemplate.round_type == ScorecardRoundType(round_type))
            count_query = count_query.where(ScorecardTemplate.round_type == ScorecardRoundType(round_type))
        if status:
            query = query.where(ScorecardTemplate.status == ScorecardStatus(status))
            count_query = count_query.where(ScorecardTemplate.status == ScorecardStatus(status))
        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(query.order_by(ScorecardTemplate.created_at.desc()).offset(skip).limit(limit))
        templates = list(result.scalars().all())
        return [await self.to_template_dict(t) for t in templates], total

    async def get_template(self, template_id: str) -> ScorecardTemplate | None:
        if not self._valid_uuid(template_id):
            return None
        result = await self.db.execute(select(ScorecardTemplate).where(ScorecardTemplate.id == template_id))
        return result.scalar_one_or_none()

    async def create_template(self, data: ScorecardTemplateCreate, created_by: str) -> ScorecardTemplate:
        round_type = ScorecardRoundType(data.round_type)
        status = ScorecardStatus(data.status)
        if status == ScorecardStatus.ACTIVE:
            await self._archive_active_templates(
                job_profile_id=data.job_profile_id,
                round_type=round_type,
            )
        template = ScorecardTemplate(
            id=str(uuid.uuid4()),
            job_profile_id=data.job_profile_id,
            profile_version_id=data.profile_version_id,
            name=data.name,
            round_type=round_type,
            status=status,
            total_weight=sum(d.weight for d in data.dimensions),
            created_by=created_by,
        )
        self.db.add(template)
        await self.db.flush()
        for dim_index, dim_data in enumerate(data.dimensions):
            dimension = ScorecardDimension(
                id=str(uuid.uuid4()),
                scorecard_template_id=template.id,
                name=dim_data.name,
                category=dim_data.category,
                weight=dim_data.weight,
                description=dim_data.description,
                required=dim_data.required,
                order_index=dim_data.order_index if dim_data.order_index else dim_index,
            )
            self.db.add(dimension)
            await self.db.flush()
            for anchor_data in dim_data.anchors:
                self.db.add(
                    ScorecardBehaviorAnchor(
                        id=str(uuid.uuid4()),
                        dimension_id=dimension.id,
                        score=anchor_data.score,
                        anchor_text=anchor_data.anchor_text,
                        evidence_examples=anchor_data.evidence_examples,
                        red_flags=anchor_data.red_flags,
                    )
                )
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def create_from_job_profile(
        self,
        profile_id: str,
        round_type: str,
        name: str | None,
        status: str,
        created_by: str,
    ) -> ScorecardTemplate | None:
        if not self._valid_uuid(profile_id):
            return None
        result = await self.db.execute(select(JobProfile).where(JobProfile.id == profile_id))
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        profile_version = await self._active_profile_version(profile.id)
        if profile_version is None:
            from app.schemas.job_profile import JobProfileVersionCreate
            from app.services.job_profile import JobProfileService

            profile_version = await JobProfileService(self.db).create_version(
                profile.id,
                JobProfileVersionCreate(change_reason="生成评分卡前固化岗位画像版本", status="active"),
                created_by=created_by,
            )
        dimensions = []
        for index, item in enumerate(profile.evaluation_dimensions or []):
            anchors = [
                {
                    "score": anchor.get("score"),
                    "anchor_text": anchor.get("evidence") or anchor.get("anchor_text") or "未提供行为锚定",
                    "evidence_examples": [],
                    "red_flags": item.get("red_flags") or [],
                }
                for anchor in item.get("scoring_guide", [])
                if anchor.get("score") is not None
            ]
            dimensions.append(
                {
                    "name": item.get("dimension") or f"维度{index + 1}",
                    "category": None,
                    "weight": item.get("weight") or 0,
                    "description": item.get("must_have"),
                    "required": True,
                    "order_index": index,
                    "anchors": anchors,
                }
            )
        if not dimensions:
            return None
        payload = ScorecardTemplateCreate(
            job_profile_id=profile.id,
            profile_version_id=profile_version.id if profile_version else None,
            name=name or f"{profile.title}-{round_type}-评分卡",
            round_type=round_type,
            status=status,
            dimensions=dimensions,
        )
        return await self.create_template(payload, created_by=created_by)

    async def get_template_for_interview(self, interview_id: str) -> dict | None:
        interview = await InterviewService(self.db)._get_by_id(interview_id)
        if interview is None:
            return None
        result = await self.db.execute(
            select(ScorecardTemplate)
            .where(ScorecardTemplate.status == ScorecardStatus.ACTIVE)
            .order_by(ScorecardTemplate.created_at.desc())
        )
        template = result.scalars().first()
        return await self.to_template_dict(template) if template else None

    async def submit_for_interview(
        self,
        interview_id: str,
        data: InterviewScorecardSubmissionCreate,
        interviewer_id: str,
    ) -> InterviewScorecardSubmission | None:
        interview = await InterviewService(self.db)._get_by_id(interview_id)
        if interview is None:
            return None
        template = await self.get_template(data.scorecard_template_id)
        if template is None:
            raise ValueError("评分卡模板不存在")
        if template.status != ScorecardStatus.ACTIVE:
            raise ValueError("只能提交 active 状态评分卡")
        dimensions = await self._dimensions_for_template(template.id)
        dimensions_by_id = {d.id: d for d in dimensions}
        score_ids = {item.dimension_id for item in data.dimension_scores}
        required_ids = {d.id for d in dimensions if d.required}
        missing = required_ids - score_ids
        if missing:
            raise ValueError("必填评分维度缺失")
        weighted = 0.0
        for item in data.dimension_scores:
            dimension = dimensions_by_id.get(item.dimension_id)
            if dimension is None:
                raise ValueError("评分维度不属于该模板")
            weighted += item.score * dimension.weight
        submission = InterviewScorecardSubmission(
            id=str(uuid.uuid4()),
            interview_id=interview.id,
            candidate_id=interview.candidate_id,
            application_id=interview.application_id,
            scorecard_template_id=template.id,
            interviewer_id=interviewer_id,
            overall_score=round(weighted, 2),
            verdict=ScorecardVerdict(data.verdict),
            summary=data.summary,
            risk_flags=data.risk_flags,
        )
        self.db.add(submission)
        await self.db.flush()
        for item in data.dimension_scores:
            self.db.add(
                InterviewScorecardDimensionScore(
                    id=str(uuid.uuid4()),
                    submission_id=submission.id,
                    dimension_id=item.dimension_id,
                    score=item.score,
                    evidence=item.evidence,
                    confidence=item.confidence,
                )
            )
        await self._sync_legacy_evaluation(interview.id, submission, data)
        await self.db.commit()
        await self.db.refresh(submission)
        return submission

    async def list_submissions_for_candidate(self, candidate_id: str) -> list[dict]:
        result = await self.db.execute(
            select(InterviewScorecardSubmission)
            .where(InterviewScorecardSubmission.candidate_id == candidate_id)
            .order_by(InterviewScorecardSubmission.submitted_at.asc())
        )
        return [await self.to_submission_dict(item) for item in result.scalars().all()]

    async def to_template_dict(self, template: ScorecardTemplate) -> dict:
        dimensions = await self._dimensions_for_template(template.id)
        anchors_by_dimension = await self._anchors_by_dimension([d.id for d in dimensions])
        return {
            "id": template.id,
            "job_profile_id": template.job_profile_id,
            "profile_version_id": template.profile_version_id,
            "name": template.name,
            "round_type": template.round_type.value,
            "status": template.status.value,
            "total_weight": template.total_weight,
            "created_by": template.created_by,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
            "dimensions": [
                {
                    "id": d.id,
                    "scorecard_template_id": d.scorecard_template_id,
                    "name": d.name,
                    "category": d.category,
                    "weight": d.weight,
                    "description": d.description,
                    "required": d.required,
                    "order_index": d.order_index,
                    "anchors": [
                        {
                            "id": a.id,
                            "dimension_id": a.dimension_id,
                            "score": a.score,
                            "anchor_text": a.anchor_text,
                            "evidence_examples": a.evidence_examples or [],
                            "red_flags": a.red_flags or [],
                        }
                        for a in anchors_by_dimension.get(d.id, [])
                    ],
                }
                for d in dimensions
            ],
        }

    async def to_submission_dict(self, submission: InterviewScorecardSubmission) -> dict:
        scores = await self._scores_for_submission(submission.id)
        dimension_ids = [s.dimension_id for s in scores]
        dimensions = await self._dimensions_by_ids(dimension_ids)
        return {
            "id": submission.id,
            "interview_id": submission.interview_id,
            "candidate_id": submission.candidate_id,
            "application_id": submission.application_id,
            "scorecard_template_id": submission.scorecard_template_id,
            "interviewer_id": submission.interviewer_id,
            "overall_score": submission.overall_score,
            "verdict": submission.verdict.value,
            "summary": submission.summary,
            "risk_flags": submission.risk_flags or [],
            "submitted_at": submission.submitted_at,
            "dimension_scores": [
                {
                    "id": s.id,
                    "submission_id": s.submission_id,
                    "dimension_id": s.dimension_id,
                    "dimension_name": dimensions.get(s.dimension_id).name if s.dimension_id in dimensions else None,
                    "score": s.score,
                    "evidence": s.evidence,
                    "confidence": s.confidence,
                }
                for s in scores
            ],
        }

    async def _sync_legacy_evaluation(
        self,
        interview_id: str,
        submission: InterviewScorecardSubmission,
        data: InterviewScorecardSubmissionCreate,
    ) -> None:
        verdict_map = {
            ScorecardVerdict.STRONG_HIRE: EvaluationVerdict.STRONG_HIRE,
            ScorecardVerdict.HIRE: EvaluationVerdict.HIRE,
            ScorecardVerdict.CONSIDER: EvaluationVerdict.CONSIDER,
            ScorecardVerdict.PASS: EvaluationVerdict.PASS,
        }
        await InterviewService(self.db).save_evaluation(
            interview_id=interview_id,
            round=InterviewRound.R2,
            overall_score=submission.overall_score,
            verdict=verdict_map[submission.verdict],
            dimensions={
                "source": "structured_scorecard",
                "scorecard_template_id": data.scorecard_template_id,
                "submission_id": submission.id,
                "dimension_scores": [item.model_dump() for item in data.dimension_scores],
            },
            key_observations=data.summary,
            red_flags="\n".join(data.risk_flags),
            feedback=data.summary,
        )

    async def _dimensions_for_template(self, template_id: str) -> list[ScorecardDimension]:
        result = await self.db.execute(
            select(ScorecardDimension)
            .where(ScorecardDimension.scorecard_template_id == template_id)
            .order_by(ScorecardDimension.order_index.asc())
        )
        return list(result.scalars().all())

    async def _active_profile_version(self, profile_id: str) -> JobProfileVersion | None:
        result = await self.db.execute(
            select(JobProfileVersion)
            .where(
                JobProfileVersion.job_profile_id == profile_id,
                JobProfileVersion.status == JobProfileVersionStatus.ACTIVE,
            )
            .order_by(JobProfileVersion.version.desc())
        )
        return result.scalars().first()

    async def _archive_active_templates(self, job_profile_id: str | None, round_type: ScorecardRoundType) -> None:
        if job_profile_id is None:
            return
        result = await self.db.execute(
            select(ScorecardTemplate).where(
                ScorecardTemplate.job_profile_id == job_profile_id,
                ScorecardTemplate.round_type == round_type,
                ScorecardTemplate.status == ScorecardStatus.ACTIVE,
            )
        )
        for existing in result.scalars().all():
            existing.status = ScorecardStatus.ARCHIVED

    async def _anchors_by_dimension(self, dimension_ids: list[str]) -> dict[str, list[ScorecardBehaviorAnchor]]:
        if not dimension_ids:
            return {}
        result = await self.db.execute(
            select(ScorecardBehaviorAnchor)
            .where(ScorecardBehaviorAnchor.dimension_id.in_(dimension_ids))
            .order_by(ScorecardBehaviorAnchor.score.asc())
        )
        grouped: dict[str, list[ScorecardBehaviorAnchor]] = {}
        for anchor in result.scalars().all():
            grouped.setdefault(anchor.dimension_id, []).append(anchor)
        return grouped

    async def _scores_for_submission(self, submission_id: str) -> list[InterviewScorecardDimensionScore]:
        result = await self.db.execute(
            select(InterviewScorecardDimensionScore).where(
                InterviewScorecardDimensionScore.submission_id == submission_id
            )
        )
        return list(result.scalars().all())

    async def _dimensions_by_ids(self, dimension_ids: list[str]) -> dict[str, ScorecardDimension]:
        if not dimension_ids:
            return {}
        result = await self.db.execute(select(ScorecardDimension).where(ScorecardDimension.id.in_(dimension_ids)))
        return {item.id: item for item in result.scalars().all()}

    @staticmethod
    def _valid_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, TypeError, AttributeError):
            return False
