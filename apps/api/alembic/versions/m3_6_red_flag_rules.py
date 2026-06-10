"""M3.6: create red_flag_rules table.

Revision ID: m3_6_red_flag_rules
Revises: m3_5_interviewer_calibration
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m3_6_red_flag_rules"
down_revision: str | Sequence[str] | None = "m3_5_interviewer_calibration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "red_flag_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_profile_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scope", sa.Enum("requirement", "dimension", "score_threshold", "tenure", "keyword", "pattern",
            name="red_flag_scope"), nullable=False
        ),
        sa.Column(
            "severity", sa.Enum("warning", "critical", name="red_flag_severity"),
            nullable=False, server_default="warning"
        ),
        sa.Column("condition_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_profile_id"], ["job_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_red_flag_rules_job_profile", "red_flag_rules", ["job_profile_id"])
    op.create_index("ix_red_flag_rules_scope", "red_flag_rules", ["scope"])
    op.create_index("ix_red_flag_rules_active", "red_flag_rules", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_red_flag_rules_active", table_name="red_flag_rules")
    op.drop_index("ix_red_flag_rules_scope", table_name="red_flag_rules")
    op.drop_index("ix_red_flag_rules_job_profile", table_name="red_flag_rules")
    op.drop_table("red_flag_rules")
    op.execute("DROP TYPE IF EXISTS red_flag_scope")
    op.execute("DROP TYPE IF EXISTS red_flag_severity")
