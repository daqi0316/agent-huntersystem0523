"""P5-11: 反垃圾/反滥用 — user 加手机字段 + sms_verification + device_fingerprint 表。

规则:
- 1 个手机号最多绑定 1 个 user
- 1 个 email 最多绑定 1 个 user (与手机独立, 用户可同时有)
- 同 IP 24h 内 ≤ 3 个邀请 (防刷邀请奖励)
- LLM token 超 100% 熔断: 拒绝新请求 + 通知 owner

Revision ID: p5_11_anti_abuse
Revises: p5_10_ai_disclosure
Create Date: 2026-06-06 14:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_11_anti_abuse"
down_revision: Union[str, Sequence[str], None] = "p5_10_ai_disclosure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_phone",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )

    op.create_table(
        "sms_verification",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False, index=True),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="register"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_phone_purpose", "sms_verification", ["phone", "purpose"])
    op.create_index("ix_sms_expires", "sms_verification", ["expires_at"])

    op.create_table(
        "device_fingerprint",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("invite_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "fingerprint_hash", name="uq_device_org_fp"),
    )
    op.create_index("ix_device_ip", "device_fingerprint", ["org_id", "ip_address"])


def downgrade() -> None:
    op.drop_index("ix_device_ip", table_name="device_fingerprint")
    op.drop_table("device_fingerprint")
    op.drop_index("ix_sms_expires", table_name="sms_verification")
    op.drop_index("ix_sms_phone_purpose", table_name="sms_verification")
    op.drop_table("sms_verification")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "phone")
