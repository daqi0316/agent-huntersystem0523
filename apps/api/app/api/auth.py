from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auto_org import get_or_create_default_org
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.core.security import create_access_token
from app.models import Membership, MembershipStatus
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.user import UserService

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """注册用户 + 自动建 default org + 返回含 current_org_id 的 token。"""
    user, _ = await UserService.register(db, data)
    org_id = await get_or_create_default_org(user.id)
    token = create_access_token(user_id=user.id, role=user.role.value if hasattr(user.role, "value") else str(user.role), current_org_id=org_id)
    return TokenResponse(access_token=token, token_type="bearer")


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录 + 自动建 default org (若无) + 返回含 current_org_id 的 token。"""
    user, _ = await UserService.login(db, data)
    org_id = await get_or_create_default_org(user.id)
    token = create_access_token(user_id=user.id, role=user.role.value if hasattr(user.role, "value") else str(user.role), current_org_id=org_id)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """返回 user + memberships (所有 org) + current_org。

    前端用 memberships 渲染 org switcher, 用 current_org 选默认 org。
    """
    from sqlalchemy import select
    from app.models import Organization
    user = await UserService.get_by_id(db, user_id)
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(404, "user not found")
    m_rows = (await db.execute(
        select(Membership, Organization)
        .join(Organization, Membership.org_id == Organization.id)
        .where(
            Membership.user_id == user_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )).all()
    memberships = [
        {
            "org_id": m.org_id,
            "org_name": org.name,
            "org_slug": org.slug,
            "org_plan": org.plan.value if hasattr(org.plan, "value") else str(org.plan),
            "role": m.role.value if hasattr(m.role, "value") else str(m.role),
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        }
        for m, org in m_rows
    ]
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "is_active": user.is_active,
        "memberships": memberships,
    }
