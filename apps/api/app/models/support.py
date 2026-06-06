"""P6-6: 客户支持工单 — 内部流转 (美洽可后接)。"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    PENDING_CUSTOMER = "pending_customer"
    PENDING_INTERNAL = "pending_internal"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class SenderType(str, enum.Enum):
    CUSTOMER = "customer"
    STAFF = "staff"
    SYSTEM = "system"


class SupportTicket(Base):
    __tablename__ = "support_ticket"
    __table_args__ = (
        Index("ix_support_ticket_org_status", "org_id", "status"),
        Index("ix_support_ticket_user_id", "user_id"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus, name="ticket_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=TicketStatus.OPEN,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        SAEnum(TicketPriority, name="ticket_priority", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=TicketPriority.NORMAL,
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportMessage(Base):
    __tablename__ = "support_message"
    __table_args__ = (
        Index("ix_support_message_ticket_id", "ticket_id"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("support_ticket.id", ondelete="CASCADE"), nullable=False)
    sender_type: Mapped[SenderType] = mapped_column(
        SAEnum(SenderType, name="sender_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    sender_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
