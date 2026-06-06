"""v0.4d: raw_resumes 表 — resume_parser 事务边界

Revision ID: v0_4d_raw_resume
Revises: p6_8_feishu_wecom
Create Date: 2026-06-06 22:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "v0_4d_raw_resume"
down_revision: Union[str, Sequence[str], None] = "p6_8_feishu_wecom"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_resumes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("file_url", sa.String(length=1024), nullable=True),
        sa.Column("file_type", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("target_job_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "processing", "parsed", "failed",
                name="raw_resume_status",
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_raw_resumes_status", "raw_resumes", ["status"])
    op.create_index("ix_raw_resumes_candidate_id", "raw_resumes", ["candidate_id"])
    op.create_index("ix_raw_resumes_target_job_id", "raw_resumes", ["target_job_id"])


def downgrade() -> None:
    op.drop_index("ix_raw_resumes_target_job_id", table_name="raw_resumes")
    op.drop_index("ix_raw_resumes_candidate_id", table_name="raw_resumes")
    op.drop_index("ix_raw_resumes_status", table_name="raw_resumes")
    op.drop_table("raw_resumes")
    op.execute("DROP TYPE IF EXISTS raw_resume_status")
