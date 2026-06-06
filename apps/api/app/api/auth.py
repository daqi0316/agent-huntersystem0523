from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auto_org import get_or_create_default_org
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.core.response import success
from app.core.security import create_access_token
from app.models import Membership, MembershipStatus, Organization
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SwitchOrgRequest,
    TokenResponse,
    UserResponse,
)
from app.services.user import UserService
from app.services.wechat_oauth import (
    WeChatOAuthError,
    exchange_code,
    find_or_create_user,
    generate_qrcode,
)

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


@router.post("/switch-org", response_model=TokenResponse)
async def switch_org(
    request: Request,
    body: SwitchOrgRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """P0-4: 切换当前 org, 返新 JWT。

    流程: 验 membership → 签新 JWT → 客户端存新 token + 替换 header + SSE 重连
    """
    r = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.org_id == body.org_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    m = r.scalar_one_or_none()
    if m is None:
        raise HTTPException(403, "not a member of this org")
    user = await UserService.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(user_id=user_id, role=role, current_org_id=body.org_id)
    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db,
        org_id=body.org_id,
        action=AuditLogAction.ORG_SWITCH,
        actor_user_id=user_id,
        request=request,
        metadata={"role": role},
    )
    await db.commit()
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
    user = await UserService.get_by_id(db, user_id)
    if user is None:
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


@router.get("/wechat/qrcode")
async def wechat_qrcode(
    redirect_uri: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """P5-2: 生成微信扫码登录二维码。

    前端调此 endpoint 拿 qrcode_url + state, 渲染二维码。
    """
    info = await generate_qrcode(db, redirect_uri=redirect_uri)
    return success(info)


@router.get("/wechat/callback")
async def wechat_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """P5-2: 微信 OAuth 回调。

    流程: 验 state → 换 user_info → 查/建 user → 签 JWT → 落 audit → 302 重定向到前端。
    """
    try:
        user_info = await exchange_code(db, code, state)
    except WeChatOAuthError as e:
        raise HTTPException(400, str(e))

    user = await find_or_create_user(
        db,
        unionid=user_info["unionid"],
        openid=user_info["openid"],
        nickname=user_info["nickname"],
        avatar_url=user_info["avatar_url"],
    )

    org_id = await get_or_create_default_org(user.id)
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(user_id=user.id, role=role, current_org_id=org_id)

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db,
        org_id=org_id,
        action=AuditLogAction.WECHAT_LOGIN,
        actor_user_id=user.id,
        request=request,
        metadata={
            "unionid": user_info["unionid"],
            "mock": settings.wechat_mock_mode,
        },
    )
    await db.commit()

    frontend_base = settings.wechat_oauth_redirect_uri.rsplit("/api/auth/wechat/callback", 1)[0]
    redirect_url = (
        f"{frontend_base}/login/wechat-callback"
        f"?token={token}&org_id={org_id}&source=wechat"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/wechat/mock-login")
async def wechat_mock_login(
    request: Request,
    code: str = Query("mock_code_001"),
    db: AsyncSession = Depends(get_db),
):
    """P5-2: Mock 一键登录 (本地开发, mock_mode=True 时可用)。

    直接调 exchange_code + find_or_create_user, 返 JWT。
    """
    if not settings.wechat_mock_mode:
        raise HTTPException(403, "mock login disabled in production")

    state_row = await generate_qrcode(db)
    state = state_row["state"]

    try:
        user_info = await exchange_code(db, code, state)
    except WeChatOAuthError as e:
        raise HTTPException(400, str(e))

    user = await find_or_create_user(
        db,
        unionid=user_info["unionid"],
        openid=user_info["openid"],
        nickname=user_info["nickname"],
        avatar_url=user_info["avatar_url"],
    )

    org_id = await get_or_create_default_org(user.id)
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(user_id=user.id, role=role, current_org_id=org_id)

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db,
        org_id=org_id,
        action=AuditLogAction.WECHAT_LOGIN,
        actor_user_id=user.id,
        request=request,
        metadata={"unionid": user_info["unionid"], "mock": True},
    )
    await db.commit()

    return success({
        "access_token": token,
        "token_type": "bearer",
        "org_id": org_id,
        "user_id": user.id,
        "unionid": user_info["unionid"],
        "mock": True,
    })
