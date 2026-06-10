"""m2_9_candidate_onboarding_tracking — OnboardingTracking / OnboardingCheckpoint / ProbationFeedback

Revision ID: m2_9
Revises: 22f9ac08ec83
Create Date: 2026-06-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "m2_9"
down_revision: str = "22f9ac08ec83"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # onboarding_trackings
    op.create_table(
        "onboarding_trackings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("offer_id", sa.String(255), nullable=True),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("manager_id", sa.String(255), nullable=True),
        sa.Column("mentor_id", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("preboarding", "onboarded", "probation", "probation_passed", "probation_failed", "resigned",
                     name="onboarding_status", values_callable=lambda x: [e.value for e in x]),
            nullable=False, server_default="preboarding", index=True,
        ),
        sa.Column(
            "risk_level",
            sa.Enum("low", "medium", "high", "critical",
                     name="onboarding_risk_level", values_callable=lambda x: [e.value for e in x]),
            nullable=False, server_default="low",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_onboarding_tracking_candidate", "onboarding_trackings", ["candidate_id"])
    op.create_index("ix_onboarding_tracking_status", "onboarding_trackings", ["status"])

    # onboarding_checkpoints
    op.create_table(
        "onboarding_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("onboarding_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("onboarding_trackings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column(
            "checkpoint_type",
            sa.Enum("day_1", "day_7", "month_1", "month_3", "month_6",
                     name="onboarding_checkpoint_type", values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "completed", "overdue", "skipped",
                     name="onboarding_checkpoint_status", values_callable=lambda x: [e.value for e in x]),
            nullable=False, server_default="pending", index=True,
        ),
        sa.Column("owner_id", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("risk_flags", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_onboarding_checkpoint_tracking", "onboarding_checkpoints", ["onboarding_id"])
    op.create_index("ix_onboarding_checkpoint_due", "onboarding_checkpoints", ["due_at"])

    # probation_feedbacks
    op.create_table(
        "probation_feedbacks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("onboarding_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("onboarding_trackings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("checkpoint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("onboarding_checkpoints.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewer_id", sa.String(255), nullable=True),
        sa.Column("performance_score", sa.Float(), nullable=True),
        sa.Column("culture_fit_score", sa.Float(), nullable=True),
        sa.Column("ramp_up_score", sa.Float(), nullable=True),
        sa.Column("communication_score", sa.Float(), nullable=True),
        sa.Column("retention_risk", sa.String(32), nullable=True),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("pass_probation", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_probation_feedback_onboarding", "probation_feedbacks", ["onboarding_id"])
    op.create_index("ix_probation_feedback_checkpoint", "probation_feedbacks", ["checkpoint_id"])


def downgrade() -> None:
    op.drop_table("probation_feedbacks")
    op.drop_table("onboarding_checkpoints")
    op.drop_table("onboarding_trackings")
    op.execute("DROP TYPE IF EXISTS onboarding_status")
    op.execute("DROP TYPE IF EXISTS onboarding_risk_level")
    op.execute("DROP TYPE IF EXISTS onboarding_checkpoint_type")
    op.execute("DROP TYPE IF EXISTS onboarding_checkpoint_status")
