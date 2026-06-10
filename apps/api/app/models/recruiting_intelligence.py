"""P2-1: 招聘结果回流 — ScorecardValidityMetric / ProfileOptimizationSuggestion / RecruitingOutcomeFeature。"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class SuggestionType(str, enum.Enum):
    WEIGHT_CHANGE = "weight_change"
    NEW_REQUIREMENT = "new_requirement"
    REMOVE_REQUIREMENT = "remove_requirement"
    NEW_QUESTION = "new_question"
    RED_FLAG = "red_flag"


class SuggestionStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ScorecardValidityMetric(Base):
    """评分卡维度有效性指标。

    追踪每个评分卡维度与试用期结果的相关性，
    用于回答"哪些面试维度最能预测试用期成功"。
    """

    __tablename__ = "scorecard_validity_metrics"
    __table_args__ = (
        Index("ix_validity_metric_template", "scorecard_template_id"),
        Index("ix_validity_metric_dimension", "dimension_id"),
        Index("ix_validity_metric_interviewer", "interviewer_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    scorecard_template_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("scorecard_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dimension_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("scorecard_dimensions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    interviewer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correlation_with_probation: Mapped[float | None] = mapped_column(Float, nullable=True)
    false_positive_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    false_negative_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_success_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProfileOptimizationSuggestion(Base):
    """画像优化建议。

    基于招聘结果数据自动生成或人工提交的建议，
    用于优化岗位画像的权重、要求项、面试问题等。
    """

    __tablename__ = "profile_optimization_suggestions"
    __table_args__ = (
        Index("ix_profile_opt_suggestion_profile", "job_profile_id"),
        Index("ix_profile_opt_suggestion_version", "profile_version_id"),
        Index("ix_profile_opt_suggestion_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_profile_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profile_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    suggestion_type: Mapped[SuggestionType] = mapped_column(
        enum_column(SuggestionType, "suggestion_type"), nullable=False, index=True
    )
    target_field: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[SuggestionStatus] = mapped_column(
        enum_column(SuggestionStatus, "suggestion_status"),
        nullable=False,
        default=SuggestionStatus.PROPOSED,
        index=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RecruitingOutcomeFeature(Base):
    """招聘结果特征。

    将候选人特征与最终结果（试用期通过/失败/离职）关联，
    供后续分析和 ML 模型使用。
    """

    __tablename__ = "recruiting_outcome_features"
    __table_args__ = (
        Index("ix_outcome_feature_candidate", "candidate_id"),
        Index("ix_outcome_feature_name", "feature_name"),
        Index("ix_outcome_feature_label", "outcome_label"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    onboarding_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("onboarding_trackings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feature_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    feature_value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_label: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
