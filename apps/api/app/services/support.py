"""P6-6: 工单 service — 创建/回复/分配/关闭。"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.support import (
    SenderType,
    SupportMessage,
    SupportTicket,
    TicketPriority,
    TicketStatus,
)


class TicketError(Exception):
    pass


async def create_ticket(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: str,
    subject: str,
    body: str,
    priority: TicketPriority = TicketPriority.NORMAL,
    category: Optional[str] = None,
) -> SupportTicket:
    if not subject.strip():
        raise TicketError("subject is required")
    if not body.strip():
        raise TicketError("body is required")
    ticket = SupportTicket(
        org_id=org_id,
        user_id=user_id,
        subject=subject.strip(),
        priority=priority,
        category=category,
    )
    db.add(ticket)
    await db.flush()
    msg = SupportMessage(
        ticket_id=ticket.id,
        sender_type=SenderType.CUSTOMER,
        sender_id=user_id,
        body=body.strip(),
    )
    db.add(msg)
    await db.flush()
    return ticket


async def add_message(
    db: AsyncSession,
    *,
    ticket_id: str,
    sender_type: SenderType,
    sender_id: Optional[str],
    body: str,
) -> SupportMessage:
    if not body.strip():
        raise TicketError("body is required")
    t = (await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )).scalar_one_or_none()
    if t is None:
        raise TicketError("ticket not found")
    if t.status in (TicketStatus.CLOSED,):
        raise TicketError("ticket is closed, reopen first")
    msg = SupportMessage(
        ticket_id=ticket_id,
        sender_type=sender_type,
        sender_id=sender_id,
        body=body.strip(),
    )
    db.add(msg)
    t.updated_at = datetime.now(UTC)
    if sender_type == SenderType.CUSTOMER:
        t.status = TicketStatus.PENDING_INTERNAL
    elif sender_type == SenderType.STAFF:
        t.status = TicketStatus.PENDING_CUSTOMER
    await db.flush()
    return msg


async def assign_ticket(db: AsyncSession, ticket_id: str, assignee_id: str) -> SupportTicket:
    t = (await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )).scalar_one_or_none()
    if t is None:
        raise TicketError("ticket not found")
    t.assigned_to = assignee_id
    t.updated_at = datetime.now(UTC)
    await db.flush()
    return t


async def resolve_ticket(db: AsyncSession, ticket_id: str) -> SupportTicket:
    t = (await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )).scalar_one_or_none()
    if t is None:
        raise TicketError("ticket not found")
    t.status = TicketStatus.RESOLVED
    t.resolved_at = datetime.now(UTC)
    t.updated_at = datetime.now(UTC)
    await db.flush()
    return t


async def close_ticket(db: AsyncSession, ticket_id: str) -> SupportTicket:
    t = (await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )).scalar_one_or_none()
    if t is None:
        raise TicketError("ticket not found")
    t.status = TicketStatus.CLOSED
    t.closed_at = datetime.now(UTC)
    t.updated_at = datetime.now(UTC)
    await db.flush()
    return t


async def list_tickets(
    db: AsyncSession,
    org_id: str,
    user_id: str,
    *,
    status: Optional[TicketStatus] = None,
    limit: int = 20,
) -> list[SupportTicket]:
    q = select(SupportTicket).where(SupportTicket.org_id == org_id, SupportTicket.user_id == user_id)
    if status is not None:
        q = q.where(SupportTicket.status == status)
    q = q.order_by(SupportTicket.updated_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_ticket_with_messages(db: AsyncSession, ticket_id: str) -> tuple[SupportTicket, list[SupportMessage]]:
    t = (await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )).scalar_one_or_none()
    if t is None:
        raise TicketError("ticket not found")
    msgs = (await db.execute(
        select(SupportMessage)
        .where(SupportMessage.ticket_id == ticket_id)
        .order_by(SupportMessage.created_at.asc())
    )).scalars().all()
    return t, list(msgs)


def serialize_ticket(t: SupportTicket) -> dict:
    return {
        "id": t.id,
        "subject": t.subject,
        "status": t.status.value,
        "priority": t.priority.value,
        "category": t.category,
        "assigned_to": t.assigned_to,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
    }


def serialize_message(m: SupportMessage) -> dict:
    return {
        "id": m.id,
        "ticket_id": m.ticket_id,
        "sender_type": m.sender_type.value,
        "sender_id": m.sender_id,
        "body": m.body,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
