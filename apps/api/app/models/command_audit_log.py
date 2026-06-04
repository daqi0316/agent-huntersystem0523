"""CommandAuditLog — 命令执行审计日志表（独立于 OperationLog）.

设计依据（plan §M2 修复）：
- 不复用 OperationLog,避免命令高频写入污染 Phase U 的物化表
- 字段专为命令系统设计,符合 V.1 退出标准
- 复合索引覆盖按"命令+时间"和"用户+时间"两个常见查询
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CommandAuditLog(Base):
    """命令执行审计日志 — 每次命令执行一条记录.

    字段对应 plan V.1 退出标准：
    - command_name / args / flags / result_code / duration_ms
    - confirmation_token / session_id / user_id / error_message / created_at
    """

    __tablename__ = "command_audit_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    command_name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="主命令名(已展开 alias)",
    )
    args: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="位置参数列表")
    flags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="--flag 字典")
    result_code: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="success | failed | denied | confirm_required | lock_timeout | not_implemented | invalid_args",
    )
    duration_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="执行耗时(毫秒)",
    )
    confirmation_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="敏感操作的确认 token",
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="会话 ID",
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True, comment="执行用户",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="失败时的错误描述",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_cmd_audit_name_time", "command_name", "created_at"),
        Index("ix_cmd_audit_user_time", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<CommandAuditLog id={self.id!r} cmd={self.command_name!r} "
            f"code={self.result_code!r} dur={self.duration_ms}ms>"
        )
