"""P5-1 补救: /audit-logs endpoint。"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.org_context import OrgContext, org_scoped_db
from app.models.audit_log import AuditLog, AuditLogAction
from app.schemas.audit_log import AuditLogList, AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])


async def log_audit(
    db: AsyncSession,
    org_id: str,
    action: AuditLogAction,
    actor_user_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    request: Optional[Request] = None,
    metadata: Optional[dict] = None,
) -> AuditLog:
    """P5-1 补救: 统一审计日志落库 helper。

    用法: 在 switch-org / invite-accept / membership-change 处调。
    """
    entry = AuditLog(
        id=str(uuid.uuid4()),
        org_id=org_id,
        actor_user_id=actor_user_id,
        action=action,
        target_user_id=target_user_id,
        meta=metadata or {},
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(entry)
    await db.flush()
    return entry


@router.get("", response_model=AuditLogList)
async def list_audit_logs(
    action: Optional[AuditLogAction] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
) -> AuditLogList:
    org_ctx, db = ctx
    q = select(AuditLog).where(AuditLog.org_id == org_ctx.org_id)
    if action is not None:
        q = q.where(AuditLog.action == action)
    q = q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    count_q = select(func.count()).select_from(AuditLog).where(AuditLog.org_id == org_ctx.org_id)
    if action is not None:
        count_q = count_q.where(AuditLog.action == action)
    total = (await db.execute(count_q)).scalar() or 0
    return AuditLogList(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total,
    )
