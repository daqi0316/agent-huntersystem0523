"""M1-6: rejection analytics fields.

Revision ID: m1_6_rejection_analytics
Revises: m1_5_job_profile_versions
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m1_6_rejection_analytics"
down_revision: str | Sequence[str] | None = "m1_5_job_profile_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    severity = postgresql.ENUM("low", "medium", "high", name="rejection_severity")
    preventable_by = postgresql.ENUM(
        "sourcing", "screening", "scorecard", "compensation", "process", "none", name="rejection_preventable_by"
    )
    source = postgresql.ENUM("human", "ai", "interviewer", "system", name="rejection_source")
    bind = op.get_bind()
    severity.create(bind, checkfirst=True)
    preventable_by.create(bind, checkfirst=True)
    source.create(bind, checkfirst=True)

    op.add_column("rejection_reasons", sa.Column("parent_id", postgresql.UUID(), nullable=True))
    op.add_column(
        "rejection_reasons",
        sa.Column(
            "severity",
            postgresql.ENUM(name="rejection_severity", create_type=False),
            nullable=False,
            server_default="medium",
        ),
    )
    op.add_column("rejection_reasons", sa.Column("stage_applicability", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column(
        "rejection_reasons",
        sa.Column(
            "preventable_by",
            postgresql.ENUM(name="rejection_preventable_by", create_type=False),
            nullable=False,
            server_default="none",
        ),
    )
    op.create_foreign_key(
        "fk_rejection_reasons_parent_id",
        "rejection_reasons",
        "rejection_reasons",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_rejection_reasons_parent_id", "rejection_reasons", ["parent_id"])
    op.create_index("ix_rejection_reasons_severity", "rejection_reasons", ["severity"])
    op.create_index("ix_rejection_reasons_preventable_by", "rejection_reasons", ["preventable_by"])

    op.add_column(
        "candidate_rejection_records",
        sa.Column(
            "source",
            postgresql.ENUM(name="rejection_source", create_type=False),
            nullable=False,
            server_default="human",
        ),
    )
    op.add_column("candidate_rejection_records", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "candidate_rejection_records",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "candidate_rejection_records",
        sa.Column("related_scorecard_submission_id", postgresql.UUID(), nullable=True),
    )
    op.add_column("candidate_rejection_records", sa.Column("related_dimension_id", postgresql.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_candidate_rejection_records_scorecard_submission",
        "candidate_rejection_records",
        "interview_scorecard_submissions",
        ["related_scorecard_submission_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_candidate_rejection_records_scorecard_dimension",
        "candidate_rejection_records",
        "scorecard_dimensions",
        ["related_dimension_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_candidate_rejection_records_source", "candidate_rejection_records", ["source"])
    op.create_index("ix_candidate_rejection_records_is_primary", "candidate_rejection_records", ["is_primary"])
    op.create_index(
        "ix_candidate_rejection_records_related_scorecard_submission_id",
        "candidate_rejection_records",
        ["related_scorecard_submission_id"],
    )
    op.create_index(
        "ix_candidate_rejection_records_related_dimension_id",
        "candidate_rejection_records",
        ["related_dimension_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_rejection_records_related_dimension_id", table_name="candidate_rejection_records")
    op.drop_index(
        "ix_candidate_rejection_records_related_scorecard_submission_id",
        table_name="candidate_rejection_records",
    )
    op.drop_index("ix_candidate_rejection_records_is_primary", table_name="candidate_rejection_records")
    op.drop_index("ix_candidate_rejection_records_source", table_name="candidate_rejection_records")
    op.drop_constraint(
        "fk_candidate_rejection_records_scorecard_dimension",
        "candidate_rejection_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_candidate_rejection_records_scorecard_submission",
        "candidate_rejection_records",
        type_="foreignkey",
    )
    op.drop_column("candidate_rejection_records", "related_dimension_id")
    op.drop_column("candidate_rejection_records", "related_scorecard_submission_id")
    op.drop_column("candidate_rejection_records", "is_primary")
    op.drop_column("candidate_rejection_records", "confidence")
    op.drop_column("candidate_rejection_records", "source")
    op.drop_index("ix_rejection_reasons_preventable_by", table_name="rejection_reasons")
    op.drop_index("ix_rejection_reasons_severity", table_name="rejection_reasons")
    op.drop_index("ix_rejection_reasons_parent_id", table_name="rejection_reasons")
    op.drop_constraint("fk_rejection_reasons_parent_id", "rejection_reasons", type_="foreignkey")
    op.drop_column("rejection_reasons", "preventable_by")
    op.drop_column("rejection_reasons", "stage_applicability")
    op.drop_column("rejection_reasons", "severity")
    op.drop_column("rejection_reasons", "parent_id")
    bind = op.get_bind()
    postgresql.ENUM(name="rejection_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="rejection_preventable_by").drop(bind, checkfirst=True)
    postgresql.ENUM(name="rejection_severity").drop(bind, checkfirst=True)
