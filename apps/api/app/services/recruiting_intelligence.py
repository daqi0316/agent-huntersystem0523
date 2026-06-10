"""P2-1: 招聘结果回流服务 — 评分卡有效性分析 / 画像优化建议 / 结果特征管理。"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recruiting_intelligence import (
    ProfileOptimizationSuggestion,
    RecruitingOutcomeFeature,
    ScorecardValidityMetric,
    SuggestionStatus,
    SuggestionType,
)
from app.models.scorecard import InterviewScorecardDimensionScore, InterviewScorecardSubmission, ScorecardDimension
from app.models.candidate_onboarding import OnboardingStatus, OnboardingTracking
from app.schemas.recruiting_intelligence import (
    OutcomeFeatureBatchCreate,
    ProfileOptimizationSuggestionCreate,
    ProfileOptimizationSuggestionUpdate,
    RecruitingOutcomeFeatureCreate,
    ValidityMetricFilter,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


# ── ScorecardValidityMetric Service ──────────────────────────────────


class ValidityMetricService:
    """评分卡维度有效性分析。

    核心逻辑：
    1. 收集每个评分卡维度的历史分数 + 对应候选人的试用期结果
    2. 计算相关性、误判率等有效性指标
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_metrics(
        self,
        filter_params: ValidityMetricFilter | None = None,
    ) -> list[ScorecardValidityMetric]:
        """重新计算并存储评分卡维度有效性指标。"""
        # 1. 构建基础查询：维度分 + 试用期结果
        rows = await self._fetch_dimension_vs_outcome(filter_params)
        if not rows:
            return []

        # 2. 按分组粒度聚合计算
        groups = self._group_and_compute(rows)
        if not groups:
            return []

        # 3. 写入 DB（替换旧数据）
        return await self._persist_metrics(groups, filter_params)

    async def _fetch_dimension_vs_outcome(
        self, filter_params: ValidityMetricFilter | None,
    ) -> list[dict[str, Any]]:
        """JOIN 评分卡维度分 → onboarding 试用期结果。

        interview_scorecard_submissions
          → interview_scorecard_dimension_scores (score, dimension_id)
          → onboarding_trackings (status: probation_passed/failed)
        """
        query = (
            select(
                InterviewScorecardDimensionScore.dimension_id,
                InterviewScorecardDimensionScore.score,
                InterviewScorecardSubmission.scorecard_template_id,
                InterviewScorecardSubmission.interviewer_id,
                OnboardingTracking.status,
                OnboardingTracking.candidate_id,
            )
            .join(
                InterviewScorecardSubmission,
                InterviewScorecardDimensionScore.submission_id == InterviewScorecardSubmission.id,
            )
            .join(
                OnboardingTracking,
                OnboardingTracking.candidate_id == InterviewScorecardSubmission.candidate_id,
            )
            .where(
                OnboardingTracking.status.in_([
                    OnboardingStatus.PROBATION_PASSED,
                    OnboardingStatus.PROBATION_FAILED,
                ])
            )
        )
        if filter_params:
            if filter_params.scorecard_template_id:
                query = query.where(
                    InterviewScorecardSubmission.scorecard_template_id == filter_params.scorecard_template_id
                )
            if filter_params.dimension_id:
                query = query.where(
                    InterviewScorecardDimensionScore.dimension_id == filter_params.dimension_id
                )
            if filter_params.interviewer_id:
                query = query.where(
                    InterviewScorecardSubmission.interviewer_id == filter_params.interviewer_id
                )
            if filter_params.min_sample_size and filter_params.min_sample_size > 0:
                query = query.having(sa_func.count() >= filter_params.min_sample_size)

        result = await self.db.execute(query)
        return [
            {
                "dimension_id": row.dimension_id,
                "score": row.score,
                "scorecard_template_id": row.scorecard_template_id,
                "interviewer_id": row.interviewer_id,
                "status": row.status.value if hasattr(row.status, "value") else row.status,
                "candidate_id": row.candidate_id,
            }
            for row in result.all()
        ]

    def _group_and_compute(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按 dimension + template + interviewer 分组，计算指标。"""
        from collections import defaultdict

        groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = (
                row["scorecard_template_id"],
                row["dimension_id"],
                row["interviewer_id"],
            )
            groups[key].append(row)

        results = []
        for (template_id, dimension_id, interviewer_id), group in groups.items():
            scores = [g["score"] for g in group]
            outcomes = [g["status"] == "probation_passed" for g in group]

            sample_size = len(scores)
            if sample_size < 2:
                continue  # 样本太少不计算

            passed = sum(1 for o in outcomes if o)
            failed = sample_size - passed
            actual_success_rate = passed / sample_size if sample_size > 0 else 0.0
            avg_score = sum(scores) / sample_size if sample_size > 0 else 0.0

            # 相关性（Pearson）：维度分 × 试用期结果 (passed=1, failed=0)
            correlation = self._pearson_correlation(scores, [1 if o else 0 for o in outcomes])

            # 误判率定义：
            # 误拒率（false negative）: 高分 (≥4) 但是试用期失败
            # 误纳率（false positive）: 低分 (≤2) 但是试用期通过
            false_negative_count = sum(
                1 for i, s in enumerate(scores) if s >= 4 and not outcomes[i]
            )
            false_positive_count = sum(
                1 for i, s in enumerate(scores) if s <= 2 and outcomes[i]
            )
            high_scorers = sum(1 for s in scores if s >= 4)
            low_scorers = sum(1 for s in scores if s <= 2)

            false_negative_rate = false_negative_count / high_scorers if high_scorers > 0 else None
            false_positive_rate = false_positive_count / low_scorers if low_scorers > 0 else None

            results.append({
                "scorecard_template_id": template_id,
                "dimension_id": dimension_id,
                "interviewer_id": interviewer_id,
                "sample_size": sample_size,
                "correlation_with_probation": correlation,
                "false_positive_rate": false_positive_rate,
                "false_negative_rate": false_negative_rate,
                "avg_score": avg_score,
                "actual_success_rate": actual_success_rate,
            })

        return results

    async def _persist_metrics(
        self, groups: list[dict[str, Any]], filter_params: ValidityMetricFilter | None,
    ) -> list[ScorecardValidityMetric]:
        """替换旧指标数据。"""
        # 清除同范围的旧记录
        delete_query = select(ScorecardValidityMetric)
        if filter_params:
            if filter_params.scorecard_template_id:
                delete_query = delete_query.where(
                    ScorecardValidityMetric.scorecard_template_id == filter_params.scorecard_template_id
                )
            if filter_params.dimension_id:
                delete_query = delete_query.where(
                    ScorecardValidityMetric.dimension_id == filter_params.dimension_id
                )
        result = await self.db.execute(delete_query)
        for old in result.scalars().all():
            await self.db.delete(old)
        await self.db.flush()

        # 写入新数据
        now = _now()
        metrics = []
        for g in groups:
            metric = ScorecardValidityMetric(
                id=str(uuid.uuid4()),
                scorecard_template_id=g["scorecard_template_id"],
                dimension_id=g["dimension_id"],
                interviewer_id=g["interviewer_id"],
                sample_size=g["sample_size"],
                correlation_with_probation=g["correlation_with_probation"],
                false_positive_rate=g["false_positive_rate"],
                false_negative_rate=g["false_negative_rate"],
                avg_score=g["avg_score"],
                actual_success_rate=g["actual_success_rate"],
                computed_at=now,
            )
            self.db.add(metric)
            metrics.append(metric)

        await self.db.commit()
        for m in metrics:
            await self.db.refresh(m)
        return metrics

    async def get_metrics(
        self, filter_params: ValidityMetricFilter | None = None,
    ) -> list[ScorecardValidityMetric]:
        """查询已计算的指标，支持过滤。"""
        query = select(ScorecardValidityMetric).order_by(
            ScorecardValidityMetric.sample_size.desc()
        )
        if filter_params:
            if filter_params.scorecard_template_id:
                query = query.where(
                    ScorecardValidityMetric.scorecard_template_id == filter_params.scorecard_template_id
                )
            if filter_params.dimension_id:
                query = query.where(
                    ScorecardValidityMetric.dimension_id == filter_params.dimension_id
                )
            if filter_params.interviewer_id:
                query = query.where(
                    ScorecardValidityMetric.interviewer_id == filter_params.interviewer_id
                )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def _pearson_correlation(x: list[float], y: list[float]) -> float | None:
        """Pearson 相关系数。"""
        n = len(x)
        if n < 2:
            return None

        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(a * b for a, b in zip(x, y))
        sum_x2 = sum(a * a for a in x)
        sum_y2 = sum(b * b for b in y)

        numerator = n * sum_xy - sum_x * sum_y
        denominator = math.sqrt((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2))

        if denominator == 0:
            return None
        r = numerator / denominator
        return max(-1.0, min(1.0, r))  # clamp 到 [-1, 1] 防浮点误差


# ── ProfileOptimizationSuggestion Service ────────────────────────────


class SuggestionService:
    """画像优化建议 CRUD + 审核流程。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, data: ProfileOptimizationSuggestionCreate,
    ) -> ProfileOptimizationSuggestion:
        suggestion = ProfileOptimizationSuggestion(
            id=str(uuid.uuid4()),
            job_profile_id=data.job_profile_id,
            profile_version_id=data.profile_version_id,
            suggestion_type=SuggestionType(data.suggestion_type),
            target_field=data.target_field,
            current_value=data.current_value,
            suggested_value=data.suggested_value,
            evidence_summary=data.evidence_summary,
            confidence=data.confidence,
            status=SuggestionStatus.PROPOSED,
            created_by=data.created_by,
        )
        self.db.add(suggestion)
        await self.db.commit()
        await self.db.refresh(suggestion)
        return suggestion

    async def list(
        self,
        job_profile_id: str | None = None,
        status: str | None = None,
        suggestion_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ProfileOptimizationSuggestion], int]:
        query = select(ProfileOptimizationSuggestion)
        count_query = select(sa_func.count(ProfileOptimizationSuggestion.id))

        if job_profile_id:
            query = query.where(ProfileOptimizationSuggestion.job_profile_id == job_profile_id)
            count_query = count_query.where(ProfileOptimizationSuggestion.job_profile_id == job_profile_id)
        if status:
            query = query.where(ProfileOptimizationSuggestion.status == SuggestionStatus(status))
            count_query = count_query.where(ProfileOptimizationSuggestion.status == SuggestionStatus(status))
        if suggestion_type:
            query = query.where(ProfileOptimizationSuggestion.suggestion_type == SuggestionType(suggestion_type))
            count_query = count_query.where(ProfileOptimizationSuggestion.suggestion_type == SuggestionType(suggestion_type))

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(ProfileOptimizationSuggestion.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get(self, suggestion_id: str) -> ProfileOptimizationSuggestion | None:
        if not _valid_uuid(suggestion_id):
            return None
        result = await self.db.execute(
            select(ProfileOptimizationSuggestion).where(ProfileOptimizationSuggestion.id == suggestion_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, suggestion_id: str, data: ProfileOptimizationSuggestionUpdate,
    ) -> ProfileOptimizationSuggestion | None:
        suggestion = await self.get(suggestion_id)
        if suggestion is None:
            return None
        if data.status:
            suggestion.status = SuggestionStatus(data.status)
        if data.reviewed_by:
            suggestion.reviewed_by = data.reviewed_by
        if data.review_notes is not None:
            suggestion.review_notes = data.review_notes
        if data.status in ("accepted", "rejected"):
            suggestion.reviewed_at = _now()
        await self.db.commit()
        await self.db.refresh(suggestion)
        return suggestion

    async def delete(self, suggestion_id: str) -> bool:
        suggestion = await self.get(suggestion_id)
        if suggestion is None:
            return False
        await self.db.delete(suggestion)
        await self.db.commit()
        return True


# ── RecruitingOutcomeFeature Service ─────────────────────────────────


class OutcomeFeatureService:
    """招聘结果特征管理。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, data: RecruitingOutcomeFeatureCreate,
    ) -> RecruitingOutcomeFeature:
        feature = RecruitingOutcomeFeature(
            id=str(uuid.uuid4()),
            candidate_id=data.candidate_id,
            application_id=data.application_id,
            onboarding_id=data.onboarding_id,
            feature_name=data.feature_name,
            feature_value=data.feature_value,
            source=data.source,
            outcome_label=data.outcome_label,
        )
        self.db.add(feature)
        await self.db.commit()
        await self.db.refresh(feature)
        return feature

    async def batch_create(self, data: OutcomeFeatureBatchCreate) -> list[RecruitingOutcomeFeature]:
        features = []
        for item in data.features:
            feature = RecruitingOutcomeFeature(
                id=str(uuid.uuid4()),
                candidate_id=item.candidate_id,
                application_id=item.application_id,
                onboarding_id=item.onboarding_id,
                feature_name=item.feature_name,
                feature_value=item.feature_value,
                source=item.source,
                outcome_label=item.outcome_label,
            )
            self.db.add(feature)
            features.append(feature)
        await self.db.commit()
        for f in features:
            await self.db.refresh(f)
        return features

    async def list(
        self,
        candidate_id: str | None = None,
        feature_name: str | None = None,
        outcome_label: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[RecruitingOutcomeFeature], int]:
        query = select(RecruitingOutcomeFeature)
        count_query = select(sa_func.count(RecruitingOutcomeFeature.id))

        if candidate_id:
            query = query.where(RecruitingOutcomeFeature.candidate_id == candidate_id)
            count_query = count_query.where(RecruitingOutcomeFeature.candidate_id == candidate_id)
        if feature_name:
            query = query.where(RecruitingOutcomeFeature.feature_name == feature_name)
            count_query = count_query.where(RecruitingOutcomeFeature.feature_name == feature_name)
        if outcome_label:
            query = query.where(RecruitingOutcomeFeature.outcome_label == outcome_label)
            count_query = count_query.where(RecruitingOutcomeFeature.outcome_label == outcome_label)

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(RecruitingOutcomeFeature.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def delete_by_candidate(self, candidate_id: str) -> int:
        result = await self.db.execute(
            select(RecruitingOutcomeFeature).where(RecruitingOutcomeFeature.candidate_id == candidate_id)
        )
        features = list(result.scalars().all())
        for f in features:
            await self.db.delete(f)
        await self.db.commit()
        return len(features)
