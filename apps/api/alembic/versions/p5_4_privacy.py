"""P5-4: 个保法 PIPL — data_export_request + data_delete_request 表

用户可要求导出/删除自己的数据, 30d 宽限期, 走 GDPR Art. 15/17 路径。

Revision ID: p5_4_privacy
Revises: p5_3_payment
Create Date: 2026-06-06 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_4_privacy"
down_revision: Union[str, Sequence[str], None] = "p5_3_payment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_export_request",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "completed", "failed", "expired", name="data_export_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("row_counts", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_export_user_status", "data_export_request", ["user_id", "status"])
    op.create_index("ix_data_export_org_status", "data_export_request", ["org_id", "status"])
    op.create_index("ix_data_export_requested_at", "data_export_request", ["requested_at"])

    op.create_table(
        "data_delete_request",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "soft_deleted", "grace_period", "hard_deleted", "cancelled", name="data_delete_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_hard_delete_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("placeholder_uuid", sa.String(length=36), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_delete_user_status", "data_delete_request", ["user_id", "status"])
    op.create_index("ix_data_delete_org_status", "data_delete_request", ["org_id", "status"])
    op.create_index("ix_data_delete_scheduled", "data_delete_request", ["scheduled_hard_delete_at"])


def downgrade() -> None:
    op.drop_index("ix_data_delete_scheduled", table_name="data_delete_request")
    op.drop_index("ix_data_delete_org_status", table_name="data_delete_request")
    op.drop_index("ix_data_delete_user_status", table_name="data_delete_request")
    op.drop_table("data_delete_request")
    op.execute("DROP TYPE IF EXISTS data_delete_status")
    op.drop_index("ix_data_export_requested_at", table_name="data_export_request")
    op.drop_index("ix_data_export_org_status", table_name="data_export_request")
    op.drop_index("ix_data_export_user_status", table_name="data_export_request")
    op.drop_table("data_export_request")
    op.execute("DROP TYPE IF EXISTS data_export_status")
