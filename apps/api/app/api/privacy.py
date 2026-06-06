"""P5-4: 个保法 PIPL API — 数据导出 + 删除 (6 endpoint)。"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.privacy import (
    DataDeleteRequest,
    DataDeleteStatus,
    DataExportRequest,
    DataExportStatus,
    EXPORT_RETENTION_DAYS,
)
from app.services.privacy import (
    PrivacyError,
    cancel_delete,
    confirm_delete,
    generate_export,
    get_export_request,
    request_delete,
    request_export,
)

router = APIRouter()


def _serialize_export(req: DataExportRequest) -> dict:
    return {
        "id": req.id,
        "status": req.status.value,
        "requested_at": req.requested_at.isoformat() if req.requested_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
        "file_size_bytes": req.file_size_bytes,
        "row_counts": req.row_counts,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "error_message": req.error_message,
        "download_path": f"/api/v1/privacy/export/{req.id}/download" if req.status == DataExportStatus.COMPLETED else None,
    }


def _serialize_delete(req: DataDeleteRequest) -> dict:
    return {
        "id": req.id,
        "status": req.status.value,
        "requested_at": req.requested_at.isoformat() if req.requested_at else None,
        "confirmed_at": req.confirmed_at.isoformat() if req.confirmed_at else None,
        "scheduled_hard_delete_at": req.scheduled_hard_delete_at.isoformat() if req.scheduled_hard_delete_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
        "cancelled_at": req.cancelled_at.isoformat() if req.cancelled_at else None,
        "placeholder_uuid": req.placeholder_uuid,
        "grace_period_days_left": (
            max(0, (req.scheduled_hard_delete_at - datetime.utcnow().replace(tzinfo=req.scheduled_hard_delete_at.tzinfo)).days)
            if req.scheduled_hard_delete_at and req.status == DataDeleteStatus.GRACE_PERIOD else None
        ),
    }


@router.post("/export", status_code=201)
async def create_export_request(
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """用户请求数据导出 (PENDING)。随后系统生成 (异步)。"""
    org_ctx, db = ctx
    try:
        req = await request_export(db, user_id=org_ctx.user_id, org_id=org_ctx.org_id)
    except PrivacyError as e:
        raise HTTPException(409, str(e))

    try:
        req = await generate_export(db, req.id)
    except PrivacyError as e:
        pass

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.DATA_EXPORT_REQUEST,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"export_request_id": req.id, "status": req.status.value},
    )
    await db.commit()
    return success(_serialize_export(req))


@router.get("/export")
async def list_export_requests(
    limit: int = Query(10, ge=1, le=50),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    rows = (await db.execute(
        select(DataExportRequest)
        .where(DataExportRequest.user_id == org_ctx.user_id)
        .order_by(DataExportRequest.requested_at.desc())
        .limit(limit)
    )).scalars().all()
    return success([_serialize_export(r) for r in rows])


@router.get("/export/{request_id}")
async def get_export(
    request_id: str,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    req = await get_export_request(db, request_id, org_ctx.user_id)
    if req is None:
        raise HTTPException(404, "export request not found")
    return success(_serialize_export(req))


@router.get("/export/{request_id}/download")
async def download_export(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Query(..., description="for ownership check, real impl use auth"),
):
    req = await get_export_request(db, request_id, user_id)
    if req is None:
        raise HTTPException(404, "export request not found")
    if req.status != DataExportStatus.COMPLETED:
        raise HTTPException(400, f"export not ready, status={req.status.value}")
    if req.expires_at and req.expires_at < datetime.utcnow().replace(tzinfo=req.expires_at.tzinfo):
        raise HTTPException(410, "export download expired (7d retention)")

    from app.core.config import settings as cfg
    from minio import Minio
    try:
        client = Minio(
            cfg.minio_endpoint, access_key=cfg.minio_access_key,
            secret_key=cfg.minio_secret_key, secure=False,
        )
        resp = client.get_object(cfg.minio_bucket, req.file_path)
        content = resp.read()
        resp.close()
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=export_{req.id}.json"},
        )
    except Exception as e:
        raise HTTPException(500, f"download failed: {e}")


@router.post("/delete", status_code=201)
async def create_delete_request(
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """用户请求删除 (PENDING)。需 confirm 才走 soft delete。"""
    org_ctx, db = ctx
    try:
        req = await request_delete(db, user_id=org_ctx.user_id, org_id=org_ctx.org_id)
    except PrivacyError as e:
        raise HTTPException(409, str(e))

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.DATA_DELETE_REQUEST,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"delete_request_id": req.id, "status": req.status.value},
    )
    await db.commit()
    return success(_serialize_delete(req))


@router.post("/delete/{request_id}/confirm")
async def confirm_delete_request(
    request_id: str,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """确认删除: PENDING → GRACE_PERIOD (is_active=False, 30d 宽限)。"""
    org_ctx, db = ctx
    try:
        req = await confirm_delete(db, request_id, org_ctx.user_id)
    except PrivacyError as e:
        raise HTTPException(400, str(e))

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.DATA_DELETE_CONFIRM,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"delete_request_id": req.id, "scheduled_at": req.scheduled_hard_delete_at.isoformat()},
    )
    await db.commit()
    return success(_serialize_delete(req))


@router.post("/delete/{request_id}/cancel")
async def cancel_delete_request(
    request_id: str,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """撤回删除: 30d 宽限期内可撤回, 恢复 is_active=True。"""
    org_ctx, db = ctx
    try:
        req = await cancel_delete(db, request_id, org_ctx.user_id)
    except PrivacyError as e:
        raise HTTPException(400, str(e))

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.DATA_DELETE_CANCEL,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"delete_request_id": req.id},
    )
    await db.commit()
    return success(_serialize_delete(req))


@router.get("/delete")
async def list_delete_requests(
    limit: int = Query(5, ge=1, le=20),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    rows = (await db.execute(
        select(DataDeleteRequest)
        .where(DataDeleteRequest.user_id == org_ctx.user_id)
        .order_by(DataDeleteRequest.requested_at.desc())
        .limit(limit)
    )).scalars().all()
    return success([_serialize_delete(r) for r in rows])
