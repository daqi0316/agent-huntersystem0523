"""p2_c_agent_experiment — add agent_experiment and agent_experiment_run tables

Revision ID: p2_c_agent_experiment
Revises: p2_c_agent_dataset
Create Date: 2026-06-10 16:30:00.000000

P2-C Stage 12: Dataset / Experiment / 回归闭环
- agent_experiment: 实验定义（名称、评估方法、配置变体）
- agent_experiment_run: 实验运行记录（结果、统计）
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p2_c_agent_experiment"
down_revision: Union[str, Sequence[str], None] = "p2_c_agent_dataset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_experiment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),

        sa.Column("dataset_item_ids", sa.Text, nullable=True,
                   comment="JSON array of dataset item IDs"),
        sa.Column("evaluator_type", sa.String(32), nullable=False, server_default="rule_based"),
        sa.Column("evaluator_config", sa.JSON, nullable=True),
        sa.Column("variants", sa.JSON, nullable=True,
                   comment="JSON array of config variants"),

        sa.Column("tags", sa.Text, nullable=True, comment="JSON array of tags"),
        sa.Column("created_by", sa.String(36), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "agent_experiment_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(36), nullable=False, index=True),
        sa.Column("variant_index", sa.Integer, nullable=False, server_default=sa.text("0")),

        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),

        sa.Column("total_items", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("passed_items", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("failed_items", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("avg_score", sa.Float, nullable=False, server_default=sa.text("0.0")),

        sa.Column("results", sa.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float, nullable=False, server_default=sa.text("0.0")),

        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("agent_experiment_run")
    op.drop_table("agent_experiment")
