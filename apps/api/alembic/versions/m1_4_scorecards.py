"""M1-4: structured interview scorecards.

Revision ID: m1_4_scorecards
Revises: m1_3_rejection_reasons
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m1_4_scorecards"
down_revision: str | Sequence[str] | None = "m1_3_rejection_reasons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    scorecard_status = postgresql.ENUM(
        "draft",
        "active",
        "archived",
        name="scorecard_status",
    )
    scorecard_round_type = postgresql.ENUM(
        "phone_screen", "technical", "behavioral", "final", "manager", name="scorecard_round_type"
    )
    scorecard_verdict = postgresql.ENUM("strong_hire", "hire", "consider", "pass", name="scorecard_verdict")
    bind = op.get_bind()
    scorecard_status.create(bind, checkfirst=True)
    scorecard_round_type.create(bind, checkfirst=True)
    scorecard_verdict.create(bind, checkfirst=True)

    op.create_table(
        "scorecard_templates",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("job_profile_id", postgresql.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "round_type",
            postgresql.ENUM(name="scorecard_round_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="scorecard_status", create_type=False),
            nullable=False,
        ),
        sa.Column("total_weight", sa.Float(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_profile_id"], ["job_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_profile_id", "round_type", "name", name="uq_scorecard_templates_profile_round_name"),
    )
    op.create_index("ix_scorecard_templates_job_profile_id", "scorecard_templates", ["job_profile_id"])
    op.create_index("ix_scorecard_templates_name", "scorecard_templates", ["name"])
    op.create_index("ix_scorecard_templates_round_type", "scorecard_templates", ["round_type"])
    op.create_index("ix_scorecard_templates_status", "scorecard_templates", ["status"])

    op.create_table(
        "scorecard_dimensions",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("scorecard_template_id", postgresql.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["scorecard_template_id"], ["scorecard_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scorecard_dimensions_scorecard_template_id", "scorecard_dimensions", ["scorecard_template_id"])
    op.create_index("ix_scorecard_dimensions_name", "scorecard_dimensions", ["name"])

    op.create_table(
        "scorecard_behavior_anchors",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("dimension_id", postgresql.UUID(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("anchor_text", sa.Text(), nullable=False),
        sa.Column("evidence_examples", sa.JSON(), nullable=False),
        sa.Column("red_flags", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["dimension_id"], ["scorecard_dimensions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scorecard_behavior_anchors_dimension_id", "scorecard_behavior_anchors", ["dimension_id"])

    op.create_table(
        "interview_scorecard_submissions",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("interview_id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("application_id", postgresql.UUID(), nullable=True),
        sa.Column("scorecard_template_id", postgresql.UUID(), nullable=False),
        sa.Column("interviewer_id", sa.String(length=255), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column(
            "verdict",
            postgresql.ENUM(name="scorecard_verdict", create_type=False),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("risk_flags", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scorecard_template_id"], ["scorecard_templates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_scorecard_submissions_interview_id",
        "interview_scorecard_submissions",
        ["interview_id"],
    )
    op.create_index(
        "ix_interview_scorecard_submissions_candidate_id",
        "interview_scorecard_submissions",
        ["candidate_id"],
    )
    op.create_index(
        "ix_interview_scorecard_submissions_application_id",
        "interview_scorecard_submissions",
        ["application_id"],
    )
    op.create_index(
        "ix_interview_scorecard_submissions_scorecard_template_id",
        "interview_scorecard_submissions",
        ["scorecard_template_id"],
    )

    op.create_table(
        "interview_scorecard_dimension_scores",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("submission_id", postgresql.UUID(), nullable=False),
        sa.Column("dimension_id", postgresql.UUID(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["dimension_id"], ["scorecard_dimensions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submission_id"], ["interview_scorecard_submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_scorecard_dimension_scores_submission_id",
        "interview_scorecard_dimension_scores",
        ["submission_id"],
    )
    op.create_index(
        "ix_interview_scorecard_dimension_scores_dimension_id",
        "interview_scorecard_dimension_scores",
        ["dimension_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_scorecard_dimension_scores_dimension_id",
        table_name="interview_scorecard_dimension_scores",
    )
    op.drop_index(
        "ix_interview_scorecard_dimension_scores_submission_id",
        table_name="interview_scorecard_dimension_scores",
    )
    op.drop_table("interview_scorecard_dimension_scores")
    op.drop_index(
        "ix_interview_scorecard_submissions_scorecard_template_id",
        table_name="interview_scorecard_submissions",
    )
    op.drop_index("ix_interview_scorecard_submissions_application_id", table_name="interview_scorecard_submissions")
    op.drop_index("ix_interview_scorecard_submissions_candidate_id", table_name="interview_scorecard_submissions")
    op.drop_index("ix_interview_scorecard_submissions_interview_id", table_name="interview_scorecard_submissions")
    op.drop_table("interview_scorecard_submissions")
    op.drop_index("ix_scorecard_behavior_anchors_dimension_id", table_name="scorecard_behavior_anchors")
    op.drop_table("scorecard_behavior_anchors")
    op.drop_index("ix_scorecard_dimensions_name", table_name="scorecard_dimensions")
    op.drop_index("ix_scorecard_dimensions_scorecard_template_id", table_name="scorecard_dimensions")
    op.drop_table("scorecard_dimensions")
    op.drop_index("ix_scorecard_templates_status", table_name="scorecard_templates")
    op.drop_index("ix_scorecard_templates_round_type", table_name="scorecard_templates")
    op.drop_index("ix_scorecard_templates_name", table_name="scorecard_templates")
    op.drop_index("ix_scorecard_templates_job_profile_id", table_name="scorecard_templates")
    op.drop_table("scorecard_templates")
    bind = op.get_bind()
    postgresql.ENUM(name="scorecard_verdict").drop(bind, checkfirst=True)
    postgresql.ENUM(name="scorecard_round_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="scorecard_status").drop(bind, checkfirst=True)
