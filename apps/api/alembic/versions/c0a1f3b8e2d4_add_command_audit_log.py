"""Add command_audit_log table for V.1 command system audit.

Revision ID: c0a1f3b8e2d4
Revises: 9e3062a04839  # normalize_candidate_status_enum (assumed head at V.1 design time)
Create Date: 2026-06-01 14:35:00.000000

设计依据（plan §M2 修复）：
- 独立于 operation_logs 表,避免命令高频写入污染 Phase U 的物化表
- 字段为命令系统定制,符合 V.1 退出标准的字段列表
- 复合索引覆盖按"命令+时间"和"用户+时间"两个常见查询
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c0a1f3b8e2d4"
down_revision: Union[str, None] = "9e3062a04839"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "command_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("command_name", sa.String(64), nullable=False,
                  comment="主命令名(已展开 alias)"),
        sa.Column("args", sa.JSON, nullable=False, server_default="[]",
                  comment="位置参数列表"),
        sa.Column("flags", sa.JSON, nullable=False, server_default="{}",
                  comment="--flag 字典"),
        sa.Column("result_code", sa.String(32), nullable=False,
                  comment="success | failed | denied | confirm_required | lock_timeout | not_implemented | invalid_args"),
        sa.Column("duration_ms", sa.Float, nullable=True,
                  comment="执行耗时(毫秒)"),
        sa.Column("confirmation_token", sa.String(64), nullable=True,
                  comment="敏感操作的确认 token"),
        sa.Column("session_id", sa.String(64), nullable=True,
                  comment="会话 ID"),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, comment="执行用户"),
        sa.Column("error_message", sa.Text, nullable=True,
                  comment="失败时的错误描述"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    # 单列索引（用于按 command_name / result_code 单独查询）
    op.create_index("ix_command_audit_log_command_name", "command_audit_log", ["command_name"])
    op.create_index("ix_command_audit_log_result_code", "command_audit_log", ["result_code"])
    op.create_index("ix_command_audit_log_confirmation_token", "command_audit_log", ["confirmation_token"])
    op.create_index("ix_command_audit_log_session_id", "command_audit_log", ["session_id"])
    op.create_index("ix_command_audit_log_user_id", "command_audit_log", ["user_id"])
    # 复合索引（覆盖两个最常见查询路径）
    op.create_index("ix_cmd_audit_name_time", "command_audit_log", ["command_name", "created_at"])
    op.create_index("ix_cmd_audit_user_time", "command_audit_log", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_cmd_audit_user_time", table_name="command_audit_log")
    op.drop_index("ix_cmd_audit_name_time", table_name="command_audit_log")
    op.drop_index("ix_command_audit_log_user_id", table_name="command_audit_log")
    op.drop_index("ix_command_audit_log_session_id", table_name="command_audit_log")
    op.drop_index("ix_command_audit_log_confirmation_token", table_name="command_audit_log")
    op.drop_index("ix_command_audit_log_result_code", table_name="command_audit_log")
    op.drop_index("ix_command_audit_log_command_name", table_name="command_audit_log")
    op.drop_table("command_audit_log")
