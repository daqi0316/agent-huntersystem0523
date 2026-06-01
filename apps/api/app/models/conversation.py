"""ConversationMessage — 持久化多轮对话消息。

每条记录表示一次 agent 交互（用户消息 → agent 回复）。
支持 session 维度的多轮历史查询和上下文注入。
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class ConversationSession(Base):
    """对话 Session — 聚合一组完整的多轮对话。

    Metadata (JSON):
      - title: 会话标题 (可由首条消息自动生成)
      - current_candidate_id: 当前讨论的候选人
      - current_job_id: 当前讨论的职位
      - last_intent: 最后识别的意图
    """

    __tablename__ = "conversation_sessions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="新对话",
    )
    session_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSON,
        nullable=True,
        default=dict,
        comment="会话上下文: current_candidate_id, last_intent, etc.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_conv_session_user", "user_id", "updated_at"),
    )


class ConversationMessage(Base):
    """单条对话消息。

    Role: user | assistant | system | tool
    每条消息对应一次 run() 的输入或输出。
    """

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="user | assistant | system | tool",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    tool_calls: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="assistant 消息的工具调用列表 (OpenAI 格式)",
    )
    tool_result: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="tool 消息的执行结果",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_conv_msg_session_created", "session_id", "created_at"),
    )
