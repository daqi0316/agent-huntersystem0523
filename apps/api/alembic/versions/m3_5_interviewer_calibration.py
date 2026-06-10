"""M3.5: create interviewer_calibration_metrics table.

Revision ID: m3_5_interviewer_calibration
Revises: m3_4_company_knowledge_items
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m3_5_interviewer_calibration"
down_revision: str | Sequence[str] | None = "m3_4_company_knowledge_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interviewer_calibration_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interviewer_id", sa.String(255), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_score", sa.Float(), nullable=True),
        sa.Column("score_stddev", sa.Float(), nullable=True),
        sa.Column("severity_bias", sa.Float(), nullable=True),
        sa.Column("correlation_with_probation", sa.Float(), nullable=True),
        sa.Column("false_positive_rate", sa.Float(), nullable=True),
        sa.Column("false_negative_rate", sa.Float(), nullable=True),
        sa.Column("strict_rate", sa.Float(), nullable=True),
        sa.Column("lenient_rate", sa.Float(), nullable=True),
        sa.Column("pass_rate", sa.Float(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calibration_interviewer", "interviewer_calibration_metrics", ["interviewer_id"])
    op.create_index("ix_calibration_period", "interviewer_calibration_metrics", ["period_start", "period_end"])


def downgrade() -> None:
    op.drop_index("ix_calibration_period", table_name="interviewer_calibration_metrics")
    op.drop_index("ix_calibration_interviewer", table_name="interviewer_calibration_metrics")
    op.drop_table("interviewer_calibration_metrics")
