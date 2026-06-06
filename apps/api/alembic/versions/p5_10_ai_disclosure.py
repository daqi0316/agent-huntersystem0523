"""P5-10: AI 监管合规 — recommendations 加 ai_score_source + 新表 appeal

依据 2026-08 生成式 AI 服务管理办法:
- AI 生成评分必须显式标识来源 (LLM/model/version/prompt_hash)
- 用户有 人工覆盖 + 申诉 权, 7d 内回复
- 所有 AI 决策 + 人工改写 落 audit

Revision ID: p5_10_ai_disclosure
Revises: p5_4_privacy
Create Date: 2026-06-06 13:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_10_ai_disclosure"
down_revision: Union[str, Sequence[str], None] = "p5_4_privacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column(
            "ai_score_source",
            sa.JSON(),
            nullable=True,
            comment="AI 评分来源: {llm, model_version, prompt_hash, generated_at}",
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "score_overridden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "score_overridden_by",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "score_overridden_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "recommendations",
        sa.Column(
            "score_override_reason",
            sa.Text(),
            nullable=True,
        ),
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "interview_evaluations" in inspector.get_table_names():
        op.add_column(
            "interview_evaluations",
            sa.Column(
                "ai_score_source",
                sa.JSON(),
                nullable=True,
                comment="AI 评估来源: {llm, model_version, prompt_hash, generated_at}",
            ),
        )
        op.add_column(
            "interview_evaluations",
            sa.Column(
                "score_overridden",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    op.create_table(
        "appeal",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "in_review", "resolved_accepted", "resolved_rejected", "cancelled", name="appeal_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(length=36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appeal_target", "appeal", ["target_type", "target_id"])
    op.create_index("ix_appeal_org_status", "appeal", ["org_id", "status"])
    op.create_index("ix_appeal_due", "appeal", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_appeal_due", table_name="appeal")
    op.drop_index("ix_appeal_org_status", table_name="appeal")
    op.drop_index("ix_appeal_target", table_name="appeal")
    op.drop_table("appeal")
    op.execute("DROP TYPE IF EXISTS appeal_status")

    op.drop_column("interview_evaluations", "score_overridden")
    op.drop_column("interview_evaluations", "ai_score_source")

    op.drop_column("recommendations", "score_override_reason")
    op.drop_column("recommendations", "score_overridden_at")
    op.drop_column("recommendations", "score_overridden_by")
    op.drop_column("recommendations", "score_overridden")
    op.drop_column("recommendations", "ai_score_source")
