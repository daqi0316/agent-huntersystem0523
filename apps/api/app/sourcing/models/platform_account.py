import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import String, Integer, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AccountType(str, Enum):
    PRIMARY = "primary"
    BACKUP = "backup"
    CRAWL = "crawl"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    BANNED = "banned"
    LIMITED = "limited"
    EXPIRED = "expired"


class PlatformAccount(Base):
    """平台账号管理"""
    __tablename__ = "sourcing_platform_accounts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    platform: Mapped[str] = mapped_column(
        String(50), ForeignKey("sourcing_platform_configs.name"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="账号标识")
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="crawl",
        comment="primary(主号)/backup(备用)/crawl(采集号)"
    )

    # 凭证（加密存储）
    encrypted_cookies: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AES 加密 Cookie")
    cookie_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 健康状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active",
        comment="active/banned/limited/expired"
    )
    daily_used: Mapped[int] = mapped_column(Integer, default=0, comment="今日已用配额")
    quota_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="配额重置时间"
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, comment="连续失败次数")
    last_banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
