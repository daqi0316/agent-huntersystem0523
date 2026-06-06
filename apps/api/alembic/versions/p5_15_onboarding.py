"""P5-15: 客户 onboarding runbook — batch_import_request + customer_health_score 表。

Excel 模板: CSV 格式 (Excel 可直开) — 候选人/职位 批量导入 + 进度跟踪。
健康度评分: 4 维度 (登录频次 40% / 功能使用 30% / 工单数 20% / 推荐行为 10%)。

Revision ID: p5_15_onboarding
Revises: p5_11_anti_abuse
Create Date: 2026-06-06 14:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_15_onboarding"
down_revision: Union[str, Sequence[str], None] = "p5_11_anti_abuse"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "batch_import_request",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "completed", "partial", "failed", name="batch_import_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("imported_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_batch_import_org_status", "batch_import_request", ["org_id", "status"])

    op.create_table(
        "customer_health_score",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("login_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("feature_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("support_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("referral_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("metrics_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_health_risk", "customer_health_score", ["risk_level"])
    op.create_index("ix_health_computed", "customer_health_score", ["computed_at"])


def downgrade() -> None:
    op.drop_index("ix_health_computed", table_name="customer_health_score")
    op.drop_index("ix_health_risk", table_name="customer_health_score")
    op.drop_table("customer_health_score")
    op.drop_index("ix_batch_import_org_status", table_name="batch_import_request")
    op.drop_table("batch_import_request")
    op.execute("DROP TYPE IF EXISTS batch_import_status")
