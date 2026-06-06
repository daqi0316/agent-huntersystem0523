"""P6-6: 工单 API — 5 endpoint (建/列/详情/回复/分配/关闭)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.support import SenderType, TicketPriority, TicketStatus
from app.services.support import (
    TicketError,
    add_message,
    assign_ticket,
    close_ticket,
    create_ticket,
    get_ticket_with_messages,
    list_tickets,
    resolve_ticket,
    serialize_message,
    serialize_ticket,
)

router = APIRouter()


class CreateTicketBody(BaseModel):
    subject: str = Field(..., min_length=1, max_length=256)
    body: str = Field(..., min_length=1, max_length=8000)
    priority: TicketPriority = TicketPriority.NORMAL
    category: str | None = None


class ReplyBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)


class AssignBody(BaseModel):
    assignee_id: str = Field(..., min_length=1)


@router.post("/tickets", status_code=201)
async def create_ticket_endpoint(
    body: CreateTicketBody,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    try:
        ticket = await create_ticket(
            db,
            user_id=org_ctx.user_id,
            org_id=org_ctx.org_id,
            subject=body.subject,
            body=body.body,
            priority=body.priority,
            category=body.category,
        )
    except TicketError as e:
        raise HTTPException(400, str(e))
    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.SUPPORT_TICKET_CREATE,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"ticket_id": ticket.id, "priority": ticket.priority.value},
    )
    await db.commit()
    return success(serialize_ticket(ticket))


@router.get("/tickets")
async def list_my_tickets(
    status: TicketStatus | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    tickets = await list_tickets(db, org_ctx.org_id, org_ctx.user_id, status=status, limit=limit)
    return success([serialize_ticket(t) for t in tickets])


@router.get("/tickets/{ticket_id}")
async def get_ticket_detail(
    ticket_id: str,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    try:
        t, msgs = await get_ticket_with_messages(db, ticket_id)
    except TicketError as e:
        raise HTTPException(404, str(e))
    if t.org_id != org_ctx.org_id or t.user_id != org_ctx.user_id:
        raise HTTPException(403, "not your ticket")
    return success({
        "ticket": serialize_ticket(t),
        "messages": [serialize_message(m) for m in msgs],
    })


@router.post("/tickets/{ticket_id}/messages", status_code=201)
async def reply_ticket(
    ticket_id: str,
    body: ReplyBody,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    try:
        t, _ = await get_ticket_with_messages(db, ticket_id)
    except TicketError as e:
        raise HTTPException(404, str(e))
    if t.org_id != org_ctx.org_id or t.user_id != org_ctx.user_id:
        raise HTTPException(403, "not your ticket")
    try:
        msg = await add_message(
            db,
            ticket_id=ticket_id,
            sender_type=SenderType.CUSTOMER,
            sender_id=org_ctx.user_id,
            body=body.body,
        )
    except TicketError as e:
        raise HTTPException(400, str(e))
    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.SUPPORT_TICKET_REPLY,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"ticket_id": ticket_id},
    )
    await db.commit()
    return success(serialize_message(msg))


@router.post("/tickets/{ticket_id}/close")
async def close_ticket_endpoint(
    ticket_id: str,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    try:
        t, _ = await get_ticket_with_messages(db, ticket_id)
    except TicketError as e:
        raise HTTPException(404, str(e))
    if t.org_id != org_ctx.org_id or t.user_id != org_ctx.user_id:
        raise HTTPException(403, "not your ticket")
    try:
        t = await close_ticket(db, ticket_id)
    except TicketError as e:
        raise HTTPException(400, str(e))
    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.SUPPORT_TICKET_CLOSE,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"ticket_id": ticket_id},
    )
    await db.commit()
    return success(serialize_ticket(t))
