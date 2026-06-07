"""v1.2: interview_evaluations 表 — E2E 真 DB 路径暴露 migration 缺失

Revision ID: v1_2_interview_evaluations
Revises: v0_4d_raw_resume
Create Date: 2026-06-07 13:00:00.000000

背景: InterviewEvaluation model 在 v0.3 已加, 但忘了建 Alembic migration.
v0.6 系列测试用 MagicMock 绕开 DB, 没碰到. v1.2 E2E 第一次 save_evaluation
真 DB 路径, 立即暴露 "relation interview_evaluations does not exist".

修复: 建表, 含 FK 到 interviews.id (CASCADE delete), enum 类型
interview_round + evaluation_verdict.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "v1_2_interview_evaluations"
down_revision: Union[str, Sequence[str], None] = "v0_4d_raw_resume"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("interview_id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column(
            "round",
            sa.Enum(
                "phone_screen", "technical", "behavioral", "final",
                name="interview_round",
            ),
            nullable=False,
        ),
        sa.Column("interviewer_id", sa.String(length=255), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column(
            "verdict",
            sa.Enum(
                "strong_hire", "hire", "consider", "pass",
                name="evaluation_verdict",
            ),
            nullable=False,
        ),
        sa.Column("dimensions", sa.Text(), nullable=True),
        sa.Column("key_observations", sa.Text(), nullable=True),
        sa.Column("red_flags", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("ai_score_source", sa.JSON(), nullable=True),
        sa.Column(
            "score_overridden",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_interview_evaluations_interview_id",
        "interview_evaluations",
        ["interview_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_interview_evaluations_interview_id", table_name="interview_evaluations")
    op.drop_table("interview_evaluations")
    sa.Enum(name="interview_round").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="evaluation_verdict").drop(op.get_bind(), checkfirst=False)
