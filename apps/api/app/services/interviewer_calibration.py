"""面试官校准服务 — 计算、查询评分偏差和误判率。"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate_onboarding import OnboardingStatus, OnboardingTracking
from app.models.interviewer_calibration import InterviewerCalibrationMetric
from app.models.scorecard import (
    InterviewScorecardDimensionScore,
    InterviewScorecardSubmission,
    ScorecardVerdict,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stddev(values: list[float]) -> float | None:
    """计算样本标准差。"""
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)


class InterviewerCalibrationService:
    """面试官校准服务。

    计算每个面试官的评分行为指标：
    - avg_score / score_stddev: 评分中心和区分度
    - severity_bias: 与全局平均分比较的相对偏差
    - strict_rate / lenient_rate: 低分/高分比例
    - pass_rate: 淘汰率
    - correlation_with_probation / false_*: 与试用期结果的相关性
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute(
        self,
        interviewer_id: str | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> list[InterviewerCalibrationMetric]:
        """计算面试官校准指标。"""
        if not period_end:
            period_end = _now()
        if not period_start:
            period_start = datetime(period_end.year - 1, period_end.month, 1, tzinfo=timezone.utc)

        # 1. 获取所有面试官提交统计
        interviewer_stats = await self._collect_interviewer_stats(
            interviewer_id, period_start, period_end
        )
        if not interviewer_stats:
            return []

        # 2. 计算全局平均分（用于 severity_bias 基准）
        all_scores = []
        for stats in interviewer_stats.values():
            all_scores.extend(stats["dimension_scores"])
        global_avg = sum(all_scores) / len(all_scores) if all_scores else 3.0

        # 3. 计算每个面试官指标
        results = []
        for iv_id, stats in interviewer_stats.items():
            dim_scores = stats["dimension_scores"]
            outcomes = stats["outcomes"]
            verdicts = stats["verdicts"]
            sample_size = len(dim_scores)

            if sample_size < 3:
                continue  # 样本太少不计算

            avg_score = sum(dim_scores) / sample_size
            score_sd = _stddev(dim_scores)

            # 严格/宽松比例
            strict_rate = sum(1 for s in dim_scores if s <= 2) / sample_size if sample_size > 0 else None
            lenient_rate = sum(1 for s in dim_scores if s >= 4) / sample_size if sample_size > 0 else None

            # 通过率 (pass verdict)
            pass_count = sum(1 for v in verdicts if v == ScorecardVerdict.PASS.value)
            pass_rate = pass_count / len(verdicts) if verdicts else None

            # 相对偏差（与全局均值的差值）
            severity_bias = avg_score - global_avg

            # 与试用期的相关性 + 误判率
            correlation = None
            false_positive_rate = None
            false_negative_rate = None
            if outcomes:
                outcome_scores = [o["score"] for o in outcomes]
                outcome_labels = [o["passed"] for o in outcomes]
                if len(outcome_scores) >= 3:
                    correlation = self._pearson_correlation(
                        outcome_scores, [1 if p else 0 for p in outcome_labels]
                    )
                    # 误判率
                    fn_count = sum(1 for i, s in enumerate(outcome_scores) if s >= 4 and not outcome_labels[i])
                    fp_count = sum(1 for i, s in enumerate(outcome_scores) if s <= 2 and outcome_labels[i])
                    high_scorers = sum(1 for s in outcome_scores if s >= 4)
                    low_scorers = sum(1 for s in outcome_scores if s <= 2)
                    false_negative_rate = fn_count / high_scorers if high_scorers > 0 else None
                    false_positive_rate = fp_count / low_scorers if low_scorers > 0 else None

            metric = InterviewerCalibrationMetric(
                id=str(uuid.uuid4()),
                interviewer_id=iv_id,
                period_start=period_start,
                period_end=period_end,
                sample_size=sample_size,
                avg_score=avg_score,
                score_stddev=score_sd,
                severity_bias=severity_bias,
                correlation_with_probation=correlation,
                false_positive_rate=false_positive_rate,
                false_negative_rate=false_negative_rate,
                strict_rate=strict_rate,
                lenient_rate=lenient_rate,
                pass_rate=pass_rate,
                computed_at=_now(),
            )
            self.db.add(metric)
            results.append(metric)

        # 4. 清除同周期旧数据
        if results:
            await self._clear_old_data(interviewer_id, period_start, period_end)

        await self.db.commit()
        for m in results:
            await self.db.refresh(m)
        return results

    async def _collect_interviewer_stats(
        self, interviewer_id: str | None, period_start: datetime, period_end: datetime,
    ) -> dict[str, dict[str, Any]]:
        """收集每个面试官的评分数据和试用期结果。"""
        query = (
            select(
                InterviewScorecardSubmission.interviewer_id,
                InterviewScorecardSubmission.verdict,
                InterviewScorecardDimensionScore.score,
                InterviewScorecardSubmission.candidate_id,
            )
            .join(
                InterviewScorecardDimensionScore,
                InterviewScorecardDimensionScore.submission_id == InterviewScorecardSubmission.id,
            )
            .where(
                InterviewScorecardSubmission.submitted_at >= period_start,
                InterviewScorecardSubmission.submitted_at <= period_end,
            )
        )
        if interviewer_id:
            query = query.where(InterviewScorecardSubmission.interviewer_id == interviewer_id)

        result = await self.db.execute(query)
        rows = result.all()

        # 按面试官聚合
        stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"dimension_scores": [], "outcomes": [], "verdicts": [], "candidate_ids": set()}
        )

        candidate_ids = set()
        for row in rows:
            iv_id = row.interviewer_id
            stats[iv_id]["dimension_scores"].append(float(row.score))
            stats[iv_id]["verdicts"].append(
                row.verdict.value if hasattr(row.verdict, "value") else row.verdict
            )
            candidate_ids.add(row.candidate_id)

        # 查询试用期结果
        if candidate_ids:
            outcome_query = (
                select(
                    InterviewScorecardSubmission.interviewer_id,
                    InterviewScorecardSubmission.candidate_id,
                    InterviewScorecardDimensionScore.score,
                    OnboardingTracking.status,
                )
                .join(
                    InterviewScorecardDimensionScore,
                    InterviewScorecardDimensionScore.submission_id == InterviewScorecardSubmission.id,
                )
                .join(
                    OnboardingTracking,
                    OnboardingTracking.candidate_id == InterviewScorecardSubmission.candidate_id,
                )
                .where(
                    InterviewScorecardSubmission.interviewer_id.in_(list(stats.keys())),
                    OnboardingTracking.status.in_([
                        OnboardingStatus.PROBATION_PASSED,
                        OnboardingStatus.PROBATION_FAILED,
                    ]),
                )
            )
            outcome_result = await self.db.execute(outcome_query)
            for outcome_row in outcome_result.all():
                iv_id = outcome_row.interviewer_id
                stats[iv_id]["outcomes"].append({
                    "score": float(outcome_row.score),
                    "passed": outcome_row.status == OnboardingStatus.PROBATION_PASSED,
                })

        return dict(stats)

    async def _clear_old_data(
        self, interviewer_id: str | None, period_start: datetime, period_end: datetime,
    ) -> None:
        """清除同周期的旧校准记录。"""
        delete_query = select(InterviewerCalibrationMetric).where(
            InterviewerCalibrationMetric.period_start == period_start,
            InterviewerCalibrationMetric.period_end == period_end,
        )
        if interviewer_id:
            delete_query = delete_query.where(
                InterviewerCalibrationMetric.interviewer_id == interviewer_id
            )
        result = await self.db.execute(delete_query)
        for old in result.scalars().all():
            await self.db.delete(old)
        await self.db.flush()

    async def list(
        self,
        interviewer_id: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[InterviewerCalibrationMetric], int]:
        """查询校准指标。"""
        query = select(InterviewerCalibrationMetric)
        count_query = select(sa_func.count(InterviewerCalibrationMetric.id))

        if interviewer_id:
            query = query.where(InterviewerCalibrationMetric.interviewer_id == interviewer_id)
            count_query = count_query.where(InterviewerCalibrationMetric.interviewer_id == interviewer_id)

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(InterviewerCalibrationMetric.computed_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_latest(self, interviewer_id: str) -> InterviewerCalibrationMetric | None:
        """获取某个面试官的最新校准指标。"""
        result = await self.db.execute(
            select(InterviewerCalibrationMetric)
            .where(InterviewerCalibrationMetric.interviewer_id == interviewer_id)
            .order_by(InterviewerCalibrationMetric.computed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

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
        return max(-1.0, min(1.0, r))
