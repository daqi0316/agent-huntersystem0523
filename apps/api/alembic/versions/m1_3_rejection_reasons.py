"""M1-3: structured rejection reasons.

Revision ID: m1_3_rejection_reasons
Revises: m1_2_job_profiles
Create Date: 2026-06-08 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "m1_3_rejection_reasons"
down_revision: Union[str, Sequence[str], None] = "m1_2_job_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REJECTION_REASONS = [
    ("TECH_DEPTH_WEAK", "技术不够", "技术深度不足", "项目和技术回答停留在表层，无法支撑目标岗位要求"),
    ("PROJECT_MISMATCH", "项目经验不匹配", "项目经验不匹配", "项目规模、复杂度、职责范围与岗位画像不匹配"),
    ("STABILITY_RISK", "稳定性", "稳定性风险", "频繁跳槽、空窗期或动机不稳定，需要记录证据"),
    ("SALARY_TOO_HIGH", "薪资", "薪资期望过高", "候选人期望明显超过岗位预算或内部公平性边界"),
    ("CULTURE_MISMATCH", "文化", "文化匹配不足", "价值观、沟通风格或团队协作方式与团队不匹配"),
    ("COMMUNICATION_WEAK", "沟通表达", "沟通表达弱", "表达不清、无法结构化说明项目或协作经历"),
    ("HARD_REQUIREMENT_MISS", "硬性条件", "硬性条件不符", "学历、年限、地点、资质等硬性条件不满足"),
    ("MOTIVATION_UNCLEAR", "动机", "动机不清晰", "求职动机、离职原因或入职意愿不清晰"),
    ("MANAGEMENT_EXPERIENCE_WEAK", "管理经验", "管理经验不足", "目标岗位需要带人或牵头，但候选人缺乏证据"),
    ("PROCESS_DROPOUT", "流程流失", "流程流失/无回复", "候选人无回复、撤回、爽约或流程中主动退出"),
]


def upgrade() -> None:
    op.create_table(
        "rejection_reasons",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_rejection_reasons_code"),
    )
    op.create_index("ix_rejection_reasons_code", "rejection_reasons", ["code"])
    op.create_index("ix_rejection_reasons_category", "rejection_reasons", ["category"])
    op.create_index("ix_rejection_reasons_is_active", "rejection_reasons", ["is_active"])

    op.create_table(
        "candidate_rejection_records",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("application_id", postgresql.UUID(), nullable=True),
        sa.Column("job_profile_id", postgresql.UUID(), nullable=True),
        sa.Column("reason_id", postgresql.UUID(), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("reason_category", sa.String(length=100), nullable=False),
        sa.Column("primary_reason", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("reusable_for_future", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("operator_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_profile_id"], ["job_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reason_id"], ["rejection_reasons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_rejection_records_candidate_id", "candidate_rejection_records", ["candidate_id"])
    op.create_index("ix_candidate_rejection_records_application_id", "candidate_rejection_records", ["application_id"])
    op.create_index("ix_candidate_rejection_records_job_profile_id", "candidate_rejection_records", ["job_profile_id"])
    op.create_index("ix_candidate_rejection_records_reason_id", "candidate_rejection_records", ["reason_id"])
    op.create_index("ix_candidate_rejection_records_reason_code", "candidate_rejection_records", ["reason_code"])
    op.create_index("ix_candidate_rejection_records_reason_category", "candidate_rejection_records", ["reason_category"])
    op.create_index("ix_candidate_rejection_records_stage", "candidate_rejection_records", ["stage"])

    for idx, (code, category, label, description) in enumerate(REJECTION_REASONS, start=1):
        op.get_bind().execute(
            sa.text(
                """
                INSERT INTO rejection_reasons (
                    id, code, category, label, description, is_active, created_at, updated_at
                ) VALUES (
                    CAST(:id AS UUID), :code, :category, :label, :description, true, now(), now()
                )
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "id": f"22222222-2222-2222-2222-2222222222{idx:02d}",
                "code": code,
                "category": category,
                "label": label,
                "description": description,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_candidate_rejection_records_stage", table_name="candidate_rejection_records")
    op.drop_index("ix_candidate_rejection_records_reason_category", table_name="candidate_rejection_records")
    op.drop_index("ix_candidate_rejection_records_reason_code", table_name="candidate_rejection_records")
    op.drop_index("ix_candidate_rejection_records_reason_id", table_name="candidate_rejection_records")
    op.drop_index("ix_candidate_rejection_records_job_profile_id", table_name="candidate_rejection_records")
    op.drop_index("ix_candidate_rejection_records_application_id", table_name="candidate_rejection_records")
    op.drop_index("ix_candidate_rejection_records_candidate_id", table_name="candidate_rejection_records")
    op.drop_table("candidate_rejection_records")
    op.drop_index("ix_rejection_reasons_is_active", table_name="rejection_reasons")
    op.drop_index("ix_rejection_reasons_category", table_name="rejection_reasons")
    op.drop_index("ix_rejection_reasons_code", table_name="rejection_reasons")
    op.drop_table("rejection_reasons")
