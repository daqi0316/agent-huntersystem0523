"""M2.7: create ai_decision_audits table + evidence_ref_id on dimension scores.

Per Section 8 of the recruiting engineering plan:
all AI decisions affecting hiring judgments must be auditable.

Revision ID: m2_7_ai_decision_audits
Revises: m2_6_evidence_refs
Create Date: 2026-06-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m2_7_ai_decision_audits"
down_revision: str | Sequence[str] | None = "m2_6_evidence_refs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    ai_decision_type = postgresql.ENUM(
        "screening", "scorecard_assist", "rejection_suggest",
        "offer_risk", "onboarding_risk", "profile_suggestion",
        name="ai_decision_type",
    )
    bind = op.get_bind()
    ai_decision_type.create(bind, checkfirst=True)

    op.create_table(
        "ai_decision_audits",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("application_id", postgresql.UUID(), nullable=True),
        sa.Column("decision_type", postgresql.ENUM(name="ai_decision_type", create_type=False), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.Text(), nullable=False),
        sa.Column("cited_standard_version_ids", sa.JSON(), nullable=False),
        sa.Column("cited_evidence_ref_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("human_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("confirmed_by", sa.String(255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_decision_audits_candidate_id", "ai_decision_audits", ["candidate_id"])
    op.create_index("ix_ai_decision_audits_application_id", "ai_decision_audits", ["application_id"])
    op.create_index("ix_ai_decision_audits_decision_type", "ai_decision_audits", ["decision_type"])

    op.add_column(
        "interview_scorecard_dimension_scores",
        sa.Column("evidence_ref_id", postgresql.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_interview_scorecard_dimension_scores_evidence_ref_id",
        "interview_scorecard_dimension_scores",
        "evidence_refs",
        ["evidence_ref_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_interview_scorecard_dimension_scores_evidence_ref_id",
        "interview_scorecard_dimension_scores",
        ["evidence_ref_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_scorecard_dimension_scores_evidence_ref_id",
        table_name="interview_scorecard_dimension_scores",
    )
    op.drop_constraint(
        "fk_interview_scorecard_dimension_scores_evidence_ref_id",
        "interview_scorecard_dimension_scores",
        type_="foreignkey",
    )
    op.drop_column("interview_scorecard_dimension_scores", "evidence_ref_id")
    op.drop_index("ix_ai_decision_audits_decision_type", table_name="ai_decision_audits")
    op.drop_index("ix_ai_decision_audits_application_id", table_name="ai_decision_audits")
    op.drop_index("ix_ai_decision_audits_candidate_id", table_name="ai_decision_audits")
    op.drop_table("ai_decision_audits")
    bind = op.get_bind()
    postgresql.ENUM(name="ai_decision_type").drop(bind, checkfirst=True)
