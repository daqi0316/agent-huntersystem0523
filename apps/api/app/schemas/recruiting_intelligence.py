"""P2-1: 招聘结果回流 schemas — ScorecardValidityMetric / ProfileOptimizationSuggestion / RecruitingOutcomeFeature。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── ScorecardValidityMetric ──────────────────────────────────────────

class ScorecardValidityMetricResponse(BaseModel):
    """评分卡维度有效性指标——只读响应。"""
    id: str
    scorecard_template_id: str | None = None
    dimension_id: str | None = None
    interviewer_id: str | None = None
    sample_size: int = 0
    correlation_with_probation: float | None = None
    false_positive_rate: float | None = None
    false_negative_rate: float | None = None
    avg_score: float | None = None
    actual_success_rate: float | None = None
    computed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ValidityMetricFilter(BaseModel):
    """查询有效性指标的过滤参数。"""
    scorecard_template_id: str | None = None
    dimension_id: str | None = None
    interviewer_id: str | None = None
    min_sample_size: int = Field(default=0, ge=0)


# ── ProfileOptimizationSuggestion ────────────────────────────────────

class ProfileOptimizationSuggestionCreate(BaseModel):
    """创建画像优化建议。"""
    job_profile_id: str
    profile_version_id: str | None = None
    suggestion_type: str = Field(..., pattern=r"^(weight_change|new_requirement|remove_requirement|new_question|red_flag)$")
    target_field: str | None = None
    current_value: str | None = None
    suggested_value: str | None = None
    evidence_summary: str | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    created_by: str = Field(..., min_length=1)


class ProfileOptimizationSuggestionUpdate(BaseModel):
    """审核/更新建议。"""
    status: str | None = Field(None, pattern=r"^(proposed|accepted|rejected)$")
    reviewed_by: str | None = None
    review_notes: str | None = None


class ProfileOptimizationSuggestionResponse(BaseModel):
    id: str
    job_profile_id: str
    profile_version_id: str | None = None
    suggestion_type: str
    target_field: str | None = None
    current_value: str | None = None
    suggested_value: str | None = None
    evidence_summary: str | None = None
    confidence: float | None = None
    status: str = "proposed"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── RecruitingOutcomeFeature ─────────────────────────────────────────

class RecruitingOutcomeFeatureCreate(BaseModel):
    """创建候选人结果特征。"""
    candidate_id: str
    application_id: str | None = None
    onboarding_id: str | None = None
    feature_name: str = Field(..., min_length=1, max_length=128)
    feature_value: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1, max_length=64)
    outcome_label: str = Field(..., min_length=1, max_length=64)


class RecruitingOutcomeFeatureResponse(BaseModel):
    id: str
    candidate_id: str
    application_id: str | None = None
    onboarding_id: str | None = None
    feature_name: str
    feature_value: str
    source: str
    outcome_label: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── 批量操作 ───────────────────────────────────────────────────────────

class OutcomeFeatureBatchCreate(BaseModel):
    """批量创建候选人结果特征。"""
    features: list[RecruitingOutcomeFeatureCreate] = Field(..., min_length=1, max_length=200)
