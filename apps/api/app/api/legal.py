"""P5-9: 法务 API — 4 endpoint (必勾清单 / 接受 / 状态 / 我的接受历史)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.legal import AgreementType
from app.services.legal import (
    get_required_agreements,
    get_user_acceptances,
    has_required_acceptances,
    record_acceptance,
    serialize_acceptance,
)

router = APIRouter()


class AcceptRequest(BaseModel):
    agreement_type: AgreementType
    confirm: bool = Field(..., description="必须 true: 明确同意的法律证据")


@router.get("/agreements")
async def list_required_agreements(
    cross_border: bool = False,
    enterprise: bool = False,
):
    return success(get_required_agreements({"cross_border": cross_border, "enterprise": enterprise}))


@router.get("/acceptances")
async def list_my_acceptances(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    accs = await get_user_acceptances(db, org_ctx.user_id)
    return success([serialize_acceptance(a) for a in accs])


@router.get("/status")
async def my_acceptance_status(
    cross_border: bool = False,
    enterprise: bool = False,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    required_types = [
        AgreementType.TERMS_OF_SERVICE,
        AgreementType.PRIVACY_POLICY,
    ]
    if cross_border or enterprise:
        required_types.append(AgreementType.DATA_PROCESSING_AGREEMENT)
    return success(await has_required_acceptances(db, org_ctx.user_id, required_types))


@router.post("/accept")
async def accept_agreement(
    body: AcceptRequest,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    if not body.confirm:
        raise HTTPException(400, "confirm must be true (explicit consent required)")

    org_ctx, db = ctx
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:512]
    acc = await record_acceptance(
        db,
        user_id=org_ctx.user_id,
        org_id=org_ctx.org_id,
        agreement_type=body.agreement_type,
        ip_address=ip,
        user_agent=ua,
    )

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.LEGAL_ACCEPTANCE,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"agreement_type": body.agreement_type.value, "version": acc.version},
    )
    await db.commit()
    return success(serialize_acceptance(acc))
