"""邀请管理 — 创建/接受/列邀请。"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import org_scoped_db
from app.core.dependencies import get_current_user_id
from app.core.security import create_access_token
from app.models import (
    Invitation,
    InvitationStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    User,
)
from app.core.response import success, error

router = APIRouter()


class CreateInvitationRequest(BaseModel):
    email: str
    role: str = Field("hr", description="owner | hr | viewer | api")


@router.post("", status_code=201)
async def create_invitation(
    body: CreateInvitationRequest,
    od = Depends(org_scoped_db),
):
    """Owner/HR 创建邀请。返 invitation (含 token)。"""
    org_ctx, db = od
    try:
        role = MembershipRole(body.role)
    except ValueError:
        raise HTTPException(400, f"invalid role: {body.role}")

    existing = (await db.execute(
        select(Invitation).where(
            Invitation.org_id == org_ctx.org_id,
            Invitation.email == body.email,
            Invitation.status == InvitationStatus.PENDING,
        )
    )).scalar_one_or_none()
    if existing is not None and existing.expires_at > datetime.now(timezone.utc):
        raise HTTPException(409, "pending invitation already exists")

    token = secrets.token_urlsafe(32)
    inv = Invitation(
        id=str(uuid.uuid4()),
        org_id=org_ctx.org_id,
        email=body.email,
        role=role,
        token=token,
        invited_by=org_ctx.user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        status=InvitationStatus.PENDING,
    )
    db.add(inv)
    await db.commit()
    return success({
        "id": inv.id,
        "email": inv.email,
        "role": inv.role.value if hasattr(inv.role, "value") else str(inv.role),
        "token": token,
        "expires_at": inv.expires_at.isoformat(),
    })


class AcceptInvitationRequest(BaseModel):
    token: str
    name: str | None = None
    password: str | None = None


@router.post("/accept", status_code=200)
async def accept_invitation(
    request: Request,
    body: AcceptInvitationRequest,
    db: AsyncSession = Depends(get_db),
):
    """接受邀请 — 用户可注册或登录, 自动加 membership, 返 token。

    流程: 验 token → 找 user (有则登录, 无则注册) → 加 membership → 签 JWT。
    """
    inv = (await db.execute(
        select(Invitation).where(
            Invitation.token == body.token,
            Invitation.status == InvitationStatus.PENDING,
        )
    )).scalar_one_or_none()
    if inv is None:
        raise HTTPException(404, "invalid or already-used invitation")
    if inv.expires_at < datetime.now(timezone.utc):
        inv.status = InvitationStatus.EXPIRED
        await db.commit()
        raise HTTPException(410, "invitation expired")

    user = (await db.execute(
        select(User).where(User.email == inv.email)
    )).scalar_one_or_none()
    if user is None:
        if not (body.name and body.password):
            raise HTTPException(400, "new user requires name + password")
        from app.core.security import hash_password
        user = User(
            id=str(uuid.uuid4()),
            email=inv.email,
            hashed_password=hash_password(body.password),
            name=body.name,
            role="hr",
        )
        db.add(user)
        await db.flush()

    existing_m = (await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.org_id == inv.org_id,
        )
    )).scalar_one_or_none()
    if existing_m is None:
        db.add(Membership(
            id=str(uuid.uuid4()),
            org_id=inv.org_id,
            user_id=user.id,
            role=inv.role,
            status=MembershipStatus.ACTIVE,
            invited_by=inv.invited_by,
            joined_at=datetime.now(timezone.utc),
        ))

    inv.status = InvitationStatus.ACCEPTED
    inv.accepted_at = datetime.now(timezone.utc)
    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db,
        org_id=inv.org_id,
        action=AuditLogAction.INVITE_ACCEPT,
        actor_user_id=user.id,
        target_user_id=user.id,
        request=request,
        metadata={"invitation_id": inv.id, "role": inv.role.value if hasattr(inv.role, "value") else str(inv.role)},
    )
    await db.commit()

    token = create_access_token(
        user_id=user.id,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        current_org_id=inv.org_id,
    )
    return success({
        "access_token": token,
        "token_type": "bearer",
        "org_id": inv.org_id,
    })


@router.get("")
async def list_invitations(
    od = Depends(org_scoped_db),
):
    """列当前 org 的邀请 (含 PENDING/ACCEPTED/EXPIRED)。"""
    org_ctx, db = od
    rows = (await db.execute(
        select(Invitation).where(Invitation.org_id == org_ctx.org_id)
    )).scalars().all()
    return success([
        {
            "id": inv.id,
            "email": inv.email,
            "role": inv.role.value if hasattr(inv.role, "value") else str(inv.role),
            "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
            "invited_at": inv.invited_at.isoformat() if inv.invited_at else None,
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
            "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
        }
        for inv in rows
    ])
