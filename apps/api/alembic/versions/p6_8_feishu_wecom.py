"""P6-8 飞书 + 企微 OAuth state 表。

Revision ID: p6_8_feishu_wecom
Revises: p6_8_dingtalk
Create Date: 2026-06-06 17:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p6_8_feishu_wecom"
down_revision: Union[str, Sequence[str], None] = "p6_8_dingtalk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("feishu_oauth_state", "wecom_oauth_state"):
        op.create_table(
            table,
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("state", sa.String(length=128), nullable=False),
            sa.Column("redirect_uri", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("state"),
        )
        op.create_index(f"ix_{table}_state", table, ["state"], unique=True)
        op.create_index(f"ix_{table}_expires_at", table, ["expires_at"])


def downgrade() -> None:
    for table in ("feishu_oauth_state", "wecom_oauth_state"):
        op.drop_index(f"ix_{table}_expires_at", table_name=table)
        op.drop_index(f"ix_{table}_state", table_name=table)
        op.drop_table(table)
