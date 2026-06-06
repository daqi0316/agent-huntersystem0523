"""P6-8 钉钉 OAuth — dingtalk_oauth_state 表。

Revision ID: p6_8_dingtalk
Revises: p6_6_support
Create Date: 2026-06-06 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p6_8_dingtalk"
down_revision: Union[str, Sequence[str], None] = "p6_6_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dingtalk_oauth_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("redirect_uri", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state"),
    )
    op.create_index("ix_dingtalk_oauth_state_state", "dingtalk_oauth_state", ["state"], unique=True)
    op.create_index("ix_dingtalk_oauth_state_expires_at", "dingtalk_oauth_state", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_dingtalk_oauth_state_expires_at", table_name="dingtalk_oauth_state")
    op.drop_index("ix_dingtalk_oauth_state_state", table_name="dingtalk_oauth_state")
    op.drop_table("dingtalk_oauth_state")
