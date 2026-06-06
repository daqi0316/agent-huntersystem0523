"""P5 in-app notification API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.notification import Notification
from app.services.notification import (
    count_unread,
    list_notifications,
    mark_all_read,
    mark_read,
)

router = APIRouter()


@router.get("/notifications")
async def list_my_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    rows = await list_notifications(db, org_ctx.user_id, org_ctx.org_id, limit, unread_only)
    return success([
        {
            "id": n.id,
            "type": n.type.value,
            "title": n.title,
            "body": n.body,
            "link": n.link,
            "read": n.read,
            "read_at": n.read_at.isoformat() if n.read_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ])


@router.get("/notifications/unread-count")
async def my_unread_count(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    return success({"unread": await count_unread(db, org_ctx.user_id, org_ctx.org_id)})


@router.post("/notifications/{notif_id}/read")
async def mark_notification_read(
    notif_id: str,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    notif = await mark_read(db, notif_id, org_ctx.user_id)
    if notif is None:
        raise HTTPException(404, "notification not found")
    return success({"id": notif.id, "read": notif.read, "read_at": notif.read_at.isoformat()})


@router.post("/notifications/read-all")
async def mark_all_my_read(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    count = await mark_all_read(db, org_ctx.user_id, org_ctx.org_id)
    return success({"marked_read": count})
