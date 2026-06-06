"""P5-9: 法务协议 — legal_acceptance 表 + 扩 audit_log_action enum。

记录 ToS/PP/DPA 用户接受, 每次协议版本变更用户必须重新接受。
audit_log_action 新增 legal_acceptance 值。

Revision ID: p5_9_legal
Revises: p5_15_onboarding
Create Date: 2026-06-06 14:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p5_9_legal"
down_revision: Union[str, Sequence[str], None] = "p5_15_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legal_acceptance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "agreement_type",
            sa.Enum("terms_of_service", "privacy_policy", "data_processing_agreement", name="agreement_type"),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_acceptance_org_id", "legal_acceptance", ["org_id"])
    op.create_index("ix_legal_acceptance_user_id", "legal_acceptance", ["user_id"])
    op.create_index(
        "ix_legal_acceptance_user_type_version",
        "legal_acceptance",
        ["user_id", "agreement_type", "version"],
        unique=True,
    )

    op.execute("ALTER TYPE audit_log_action ADD VALUE IF NOT EXISTS 'legal_acceptance'")


def downgrade() -> None:
    op.drop_index("ix_legal_acceptance_user_type_version", table_name="legal_acceptance")
    op.drop_index("ix_legal_acceptance_user_id", table_name="legal_acceptance")
    op.drop_index("ix_legal_acceptance_org_id", table_name="legal_acceptance")
    op.drop_table("legal_acceptance")
    sa.Enum(name="agreement_type").drop(op.get_bind(), checkfirst=True)
