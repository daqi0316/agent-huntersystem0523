"""p2_c_agent_feedback — add agent_feedback table for Stage 11

Revision ID: p2_c_agent_feedback
Revises: p2_a_business_events
Create Date: 2026-06-10 14:39:17.663002

P2-C Stage 11: 用户反馈与人工标注
- category: 反馈类别（枚举可扩展）
- source: 反馈来源（end_user/annotator/auto_rule/auto_eval）
- score: [0.0, 1.0] 评分
- trace_id / span_id / message_id / session_id: 关联 AgentOps 执行链路
- user_id: 提交反馈的用户
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p2_c_agent_feedback"
down_revision: Union[str, Sequence[str], None] = "p2_a_business_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(32), nullable=False, index=True),
        sa.Column("source", sa.String(32), nullable=False, index=True, server_default="end_user"),
        sa.Column("score", sa.Float, nullable=False),

        # 反馈文本理由
        sa.Column("reason", sa.Text, nullable=True),

        # 执行链路关联
        sa.Column("trace_id", sa.String(36), nullable=True, index=True),
        sa.Column("span_id", sa.String(36), nullable=True),
        sa.Column("message_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),

        # 业务实体关联
        sa.Column("target_entity_type", sa.String(32), nullable=True),
        sa.Column("target_entity_id", sa.String(36), nullable=True),

        # 用户
        sa.Column("user_id", sa.String(36), nullable=True, index=True),

        # 标签与元数据
        sa.Column("tags", sa.Text, nullable=True, comment="JSON array of tags"),
        sa.Column("metadata_json", sa.JSON, nullable=True),

        # 审计时间戳
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True,
                   comment="反馈创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                   comment="最后更新时间"),
    )


def downgrade() -> None:
    op.drop_table("agent_feedback")
