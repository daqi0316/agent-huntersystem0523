"""P5-2: 微信扫码登录 — User 加 WeChat 字段 + wechat_oauth_state 表

Revision ID: p5_2_wechat_oauth
Revises: p5_1_remediation_audit_log
Create Date: 2026-06-06 02:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_2_wechat_oauth"
down_revision: Union[str, Sequence[str], None] = "p5_1_remediation_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users 表加 WeChat 字段
    op.add_column(
        "users",
        sa.Column("wechat_unionid", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("wechat_openid", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("wechat_nickname", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("wechat_avatar_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_source",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'email'"),
        ),
    )
    # partial unique index: 仅当 unionid 非空时唯一 (允许老 email 用户 NULL)
    op.create_index(
        "ix_users_wechat_unionid",
        "users",
        ["wechat_unionid"],
        unique=True,
        postgresql_where=sa.text("wechat_unionid IS NOT NULL"),
    )

    # 2. wechat_oauth_state 表 (CSRF state + 重放保护)
    op.create_table(
        "wechat_oauth_state",
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("redirect_uri", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        "ix_wechat_oauth_state_expires",
        "wechat_oauth_state",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_wechat_oauth_state_expires", table_name="wechat_oauth_state")
    op.drop_table("wechat_oauth_state")
    op.drop_index("ix_users_wechat_unionid", table_name="users")
    op.drop_column("users", "auth_source")
    op.drop_column("users", "wechat_avatar_url")
    op.drop_column("users", "wechat_nickname")
    op.drop_column("users", "wechat_openid")
    op.drop_column("users", "wechat_unionid")
