"""M2.2: compensation database.

Revision ID: m2_2_compensation
Revises: m2_1_candidate_timeline
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m2_2_compensation"
down_revision: str | Sequence[str] | None = "m2_1_candidate_timeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    status = postgresql.ENUM("draft", "negotiating", "accepted", "rejected", "withdrawn", name="offer_negotiation_status")
    status.create(bind, checkfirst=True)
    op.create_table(
        "compensation_benchmarks",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("job_family", sa.String(length=128), nullable=False),
        sa.Column("job_title", sa.String(length=255), nullable=False),
        sa.Column("level", sa.String(length=64), nullable=False),
        sa.Column("company_type", sa.String(length=128), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("base_min", sa.Float(), nullable=True),
        sa.Column("base_p50", sa.Float(), nullable=True),
        sa.Column("base_max", sa.Float(), nullable=True),
        sa.Column("total_min", sa.Float(), nullable=True),
        sa.Column("total_p50", sa.Float(), nullable=True),
        sa.Column("total_max", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), server_default="CNY", nullable=False),
        sa.Column("period", sa.String(length=32), server_default="year", nullable=False),
        sa.Column("data_source", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("industry", "city", "job_family", "job_title", "level"):
        op.create_index(f"ix_compensation_benchmarks_{col}", "compensation_benchmarks", [col])
    op.create_index("ix_comp_benchmarks_lookup", "compensation_benchmarks", ["city", "job_family", "job_title", "level"])
    op.create_table(
        "candidate_compensation_expectations",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("current_base", sa.Float(), nullable=True),
        sa.Column("current_total", sa.Float(), nullable=True),
        sa.Column("expected_base", sa.Float(), nullable=True),
        sa.Column("expected_total", sa.Float(), nullable=True),
        sa.Column("minimum_acceptable", sa.Float(), nullable=True),
        sa.Column("notice_period", sa.String(length=128), nullable=True),
        sa.Column("competing_offers", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_comp_expect_candidate", "candidate_compensation_expectations", ["candidate_id"])
    op.create_table(
        "offer_negotiation_records",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("application_id", postgresql.UUID(), nullable=True),
        sa.Column("job_id", postgresql.UUID(), nullable=True),
        sa.Column("expected_total", sa.Float(), nullable=True),
        sa.Column("first_offer_total", sa.Float(), nullable=True),
        sa.Column("final_offer_total", sa.Float(), nullable=True),
        sa.Column("market_p50", sa.Float(), nullable=True),
        sa.Column("budget_min", sa.Float(), nullable=True),
        sa.Column("budget_max", sa.Float(), nullable=True),
        sa.Column("negotiation_status", postgresql.ENUM(name="offer_negotiation_status", create_type=False), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("reject_reason", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["job_positions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("candidate_id", "application_id", "job_id", "negotiation_status"):
        op.create_index(f"ix_offer_negotiation_records_{col}", "offer_negotiation_records", [col])
    op.create_index("ix_offer_negotiation_candidate_created", "offer_negotiation_records", ["candidate_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_offer_negotiation_candidate_created", table_name="offer_negotiation_records")
    for col in ("negotiation_status", "job_id", "application_id", "candidate_id"):
        op.drop_index(f"ix_offer_negotiation_records_{col}", table_name="offer_negotiation_records")
    op.drop_table("offer_negotiation_records")
    op.drop_index("ix_candidate_comp_expect_candidate", table_name="candidate_compensation_expectations")
    op.drop_table("candidate_compensation_expectations")
    op.drop_index("ix_comp_benchmarks_lookup", table_name="compensation_benchmarks")
    for col in ("level", "job_title", "job_family", "city", "industry"):
        op.drop_index(f"ix_compensation_benchmarks_{col}", table_name="compensation_benchmarks")
    op.drop_table("compensation_benchmarks")
    postgresql.ENUM(name="offer_negotiation_status").drop(op.get_bind(), checkfirst=True)
