import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Approval(Base):
    """审批记录 — DB 持久化，替代 HumanLoopAgent 内存 pending_approvals。"""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="candidate / interview / job")
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        enum_column(ApprovalStatus, "approval_status"),
        nullable=False,
        default=ApprovalStatus.PENDING,
        index=True,
    )
    proposal: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    candidate_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolver_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="审批人 user_id",
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True, comment="审批意见")
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
