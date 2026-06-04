"""add operation_stats_hourly table

Background: 2026-06-03 后端僵死事故根因。
``OperationStatsHourly`` model 已定义但 alembic 缺 migration，
DB 无此表，导致 ``aggregation_loop`` 后台任务和
``/dashboard/operations/{summary,trend}`` 端点抛 UndefinedTableError，
asyncpg 连接累积泄漏到 pool 耗尽（30 个连接），所有 endpoint 卡死。

修复: 补建表 + 配套 unique constraint。
运行: ``alembic upgrade head`` 即可在 dev / prod 一致建表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c0e2f3b4d5"
down_revision: Union[str, Sequence[str], None] = "merge_heads_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operation_stats_hourly",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("bucket_hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("total_ops", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("system_error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_duration_ms", sa.Float(), nullable=True),
        sa.Column("p50_duration_ms", sa.Float(), nullable=True),
        sa.Column("p95_duration_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("bucket_hour", "agent_name", name="uq_stats_hour_agent"),
    )
    op.create_index(
        "ix_operation_stats_hourly_bucket_hour",
        "operation_stats_hourly",
        ["bucket_hour"],
    )


def downgrade() -> None:
    op.drop_index("ix_operation_stats_hourly_bucket_hour", table_name="operation_stats_hourly")
    op.drop_table("operation_stats_hourly")
