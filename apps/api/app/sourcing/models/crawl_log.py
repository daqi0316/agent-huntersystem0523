import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import String, Integer, DateTime, Float, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CrawlStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BANNED = "banned"
    ACCOUNT_BANNED = "account_banned"
    CAPTCHA = "captcha"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    SKIPPED = "skipped"


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("sourcing_tasks.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, comment="平台标识")
    url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="目标 URL")
    page: Mapped[int] = mapped_column(Integer, default=1, comment="页码")

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    proxy_used: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="使用的代理")
    account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("sourcing_platform_accounts.id"),
        nullable=True, index=True, comment="关联平台账号"
    )
    captcha_solved: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="重试次数")

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 关联
    task = relationship("SourcingTask", back_populates="logs")
