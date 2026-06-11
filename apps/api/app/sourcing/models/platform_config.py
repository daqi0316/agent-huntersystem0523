from datetime import datetime
from enum import Enum

from sqlalchemy import String, Integer, DateTime, Boolean
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PlatformConfig(Base):
    __tablename__ = "sourcing_platform_configs"

    name: Mapped[str] = mapped_column(String(50), primary_key=True, comment="平台标识")
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, comment="job_board/social/code/academic")
    anti_crawl_level: Mapped[int] = mapped_column(Integer, default=3, comment="1-5")
    requires_login: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit: Mapped[int] = mapped_column(Integer, default=3, comment="请求间隔(秒)")
    daily_quota_per_account: Mapped[int] = mapped_column(Integer, default=300, comment="每账号日配额")

    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, comment="平台特有配置")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
