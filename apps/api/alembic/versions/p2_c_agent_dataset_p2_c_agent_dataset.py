"""p2_c_agent_dataset — add agent_dataset_item table for Stage 12

Revision ID: p2_c_agent_dataset
Revises: p2_c_agent_feedback
Create Date: 2026-06-10 16:00:00.000000

P2-C Stage 12: Dataset / Experiment / 回归闭环
- 存储回归测试集数据项
- 支持从 feedback bad_case 自动生成
- 为 Experiment runner 提供数据源
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p2_c_agent_dataset"
down_revision: Union[str, Sequence[str], None] = "p2_c_agent_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_dataset_item",
        sa.Column("id", sa.String(36), primary_key=True),

        # 分类与来源
        sa.Column("category", sa.String(32), nullable=False, index=True,
                   comment="业务分类: resume_parse/screening/jd_generation/..."),
        sa.Column("source", sa.String(32), nullable=False, index=True, server_default="manual",
                   comment="来源: bad_case/system_failure/annotation/manual/sampled"),

        # 执行链路关联
        sa.Column("trace_id", sa.String(36), nullable=True, index=True),
        sa.Column("span_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),

        # 业务实体关联
        sa.Column("entity_type", sa.String(32), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),

        # 核心数据快照
        sa.Column("input_snapshot", sa.JSON, nullable=True,
                   comment="输入快照（脱敏后）"),
        sa.Column("expected_output", sa.JSON, nullable=True,
                   comment="预期输出（标注/修正后）"),
        sa.Column("actual_output", sa.JSON, nullable=True,
                   comment="实际输出（原始 Agent 输出）"),

        # 反馈关联
        sa.Column("feedback_id", sa.String(36), nullable=True, index=True),

        # 标签与描述
        sa.Column("tags", sa.Text, nullable=True, comment="JSON array of tags"),
        sa.Column("is_bad_case", sa.Boolean, nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("description", sa.Text, nullable=True),

        # 人工修正
        sa.Column("corrected_output", sa.JSON, nullable=True),
        sa.Column("correction_notes", sa.Text, nullable=True),

        # 评分与优先级
        sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("score", sa.Float, nullable=False, server_default=sa.text("0.0")),

        # 自由元数据
        sa.Column("metadata_json", sa.JSON, nullable=True),

        # 审计时间戳
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True,
                   comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                   comment="最后更新时间"),
    )


def downgrade() -> None:
    op.drop_table("agent_dataset_item")
