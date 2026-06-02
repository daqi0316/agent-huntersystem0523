"""add_operation_logs_table

Revision ID: a1b2c3d4e5f6
Revises: b2a4d6f3e9c8
Create Date: 2026-06-02 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "b2a4d6f3e9c8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "operation_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.String(17),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_category", sa.String(16), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "immutable",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("superseded_by", sa.String(36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index("idx_oplog_user_id", "operation_logs", ["user_id"])
    op.create_index("idx_oplog_agent_name", "operation_logs", ["agent_name"])
    op.create_index(
        "idx_oplog_agent_status_created",
        "operation_logs",
        ["agent_name", "status", "created_at"],
    )
    op.create_index("idx_oplog_error_cat", "operation_logs", ["error_category", "created_at"])


def downgrade() -> None:
    op.drop_table("operation_logs")
