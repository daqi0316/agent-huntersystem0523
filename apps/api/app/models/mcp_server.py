import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class MCPServer(Base):
    """已配置的外部 MCP Server — 运行时 Agent 可发现并使用其工具。"""

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="用户自定义名称，如「邮件助手」"
    )
    server_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="MCP server HTTP endpoint"
    )
    protocol: Mapped[str] = mapped_column(
        String(32), nullable=False, default="streamable-http",
        comment="传输协议: streamable-http | sse",
    )
    auth_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none",
        comment="认证方式: none | bearer | basic",
    )
    auth_token: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="凭证（加密存储）"
    )
    tools_cache: Mapped[dict | None] = mapped_column(
        # JSON stored as Text — SQLAlchemy handles via type annotation
        Text, nullable=True,
        comment="缓存的工具列表 JSON",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
