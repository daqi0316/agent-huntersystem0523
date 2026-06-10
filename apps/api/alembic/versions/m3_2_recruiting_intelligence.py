"""m3_2: 招聘结果回流 — scorecard_validity_metrics / profile_optimization_suggestions / recruiting_outcome_features。

P2-1: 数据智能层第一部分，为招聘结果回流提供基础表：
  - scorecard_validity_metrics: 评分卡维度与试用期结果的相关性
  - profile_optimization_suggestions: 画像优化建议
  - recruiting_outcome_features: 候选人特征与结果标签

Revision ID: m3_2_recruiting_intelligence
Revises: m3_1_onboarding_check_constraints
Create Date: 2026-06-09 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "m3_2_recruiting_intelligence"
down_revision: Union[str, Sequence[str], None] = "m3_1_onboarding_check_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === scorecard_validity_metrics ===
    op.create_table(
        "scorecard_validity_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("scorecard_template_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("scorecard_templates.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("dimension_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("scorecard_dimensions.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("interviewer_id", sa.String(255), nullable=True, index=True),
        sa.Column("sample_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correlation_with_probation", sa.Float, nullable=True),
        sa.Column("false_positive_rate", sa.Float, nullable=True),
        sa.Column("false_negative_rate", sa.Float, nullable=True),
        sa.Column("avg_score", sa.Float, nullable=True),
        sa.Column("actual_success_rate", sa.Float, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_validity_metric_template", "scorecard_validity_metrics", ["scorecard_template_id"])
    op.create_index("ix_validity_metric_dimension", "scorecard_validity_metrics", ["dimension_id"])
    op.create_index("ix_validity_metric_interviewer", "scorecard_validity_metrics", ["interviewer_id"])

    # === profile_optimization_suggestions ===
    op.create_table(
        "profile_optimization_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("job_profile_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("job_profiles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("job_profile_versions.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("suggestion_type", sa.String(32), sa.CheckConstraint("suggestion_type IN ('weight_change','new_requirement','remove_requirement','new_question','red_flag')"), nullable=False, index=True),
        sa.Column("target_field", sa.String(255), nullable=True),
        sa.Column("current_value", sa.Text, nullable=True),
        sa.Column("suggested_value", sa.Text, nullable=True),
        sa.Column("evidence_summary", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("status", sa.String(16), sa.CheckConstraint("status IN ('proposed','accepted','rejected')"), nullable=False, server_default="proposed", index=True),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_profile_opt_suggestion_profile", "profile_optimization_suggestions", ["job_profile_id"])
    op.create_index("ix_profile_opt_suggestion_version", "profile_optimization_suggestions", ["profile_version_id"])
    op.create_index("ix_profile_opt_suggestion_status", "profile_optimization_suggestions", ["status"])

    # === recruiting_outcome_features ===
    op.create_table(
        "recruiting_outcome_features",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("onboarding_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("onboarding_trackings.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("feature_name", sa.String(128), nullable=False, index=True),
        sa.Column("feature_value", sa.Text, nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("outcome_label", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_outcome_feature_candidate", "recruiting_outcome_features", ["candidate_id"])
    op.create_index("ix_outcome_feature_name", "recruiting_outcome_features", ["feature_name"])
    op.create_index("ix_outcome_feature_label", "recruiting_outcome_features", ["outcome_label"])


def downgrade() -> None:
    op.drop_table("recruiting_outcome_features")
    op.drop_table("profile_optimization_suggestions")
    op.drop_table("scorecard_validity_metrics")
