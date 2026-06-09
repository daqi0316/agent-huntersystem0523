"""M2.6: create evidence_refs table.

Per Section 6 of the recruiting engineering plan:
unified evidence reference protocol for all AI/human judgments.

Revision ID: m2_6_evidence_refs
Revises: m2_5_version_protocol
Create Date: 2026-06-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m2_6_evidence_refs"
down_revision: str | Sequence[str] | None = "m2_5_version_protocol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    evidence_source_type = postgresql.ENUM(
        "resume", "interview", "scorecard", "rejection",
        "timeline", "compensation", "onboarding", "knowledge",
        name="evidence_source_type",
    )
    evidence_created_by_type = postgresql.ENUM(
        "human", "ai", "system",
        name="evidence_created_by_type",
    )
    bind = op.get_bind()
    evidence_source_type.create(bind, checkfirst=True)
    evidence_created_by_type.create(bind, checkfirst=True)

    op.create_table(
        "evidence_refs",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("application_id", postgresql.UUID(), nullable=True),
        sa.Column("source_type", postgresql.ENUM(name="evidence_source_type", create_type=False), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("normalized_claim", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_by_type", postgresql.ENUM(name="evidence_created_by_type", create_type=False), nullable=False),
        sa.Column("created_by_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_evidence_refs_confidence_range",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_refs_candidate_id", "evidence_refs", ["candidate_id"])
    op.create_index("ix_evidence_refs_application_id", "evidence_refs", ["application_id"])
    op.create_index("ix_evidence_refs_source_type", "evidence_refs", ["source_type"])
    op.create_index("ix_evidence_refs_source_id", "evidence_refs", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_refs_source_id", table_name="evidence_refs")
    op.drop_index("ix_evidence_refs_source_type", table_name="evidence_refs")
    op.drop_index("ix_evidence_refs_application_id", table_name="evidence_refs")
    op.drop_index("ix_evidence_refs_candidate_id", table_name="evidence_refs")
    op.drop_table("evidence_refs")
    bind = op.get_bind()
    postgresql.ENUM(name="evidence_created_by_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="evidence_source_type").drop(bind, checkfirst=True)
