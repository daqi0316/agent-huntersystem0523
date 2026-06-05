"""P5-1 PR 3 — Org context 中间件。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.security import decode_access_token
from app.models import Membership, MembershipStatus


@dataclass
class OrgContext:
    org_id: str
    user_id: str
    role: str


async def apply_rls_context(db: AsyncSession, org_id: str) -> None:
    """P0-2: 在 transaction 内 set_config() (RLS 谓词生效)。

    用 SELECT set_config() 而非 SET LOCAL — 后者不支持 prepared statement 参数绑定。
    set_config 第三个参数 true = LOCAL (per transaction)。
    """
    await db.execute(
        text("SELECT set_config('app.current_org_id', :oid, true)"),
        {"oid": org_id},
    )


async def get_org_context(request: Request) -> OrgContext:
    """FastAPI dependency: 解析 token → 验 membership → 返 OrgContext。"""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "missing token")
    token = auth.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
    except Exception as e:
        raise HTTPException(401, f"invalid token: {e}")
    user_id = payload.get("sub")
    org_id = payload.get("current_org_id") or payload.get("org_id")
    if not user_id or not org_id:
        raise HTTPException(401, "token missing sub or current_org_id")

    async with AsyncSessionLocal() as session:
        r = await session.execute(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.org_id == org_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        m = r.scalar_one_or_none()
        if m is None:
            raise HTTPException(403, "not a member of this org")
        role = m.role.value if hasattr(m.role, "value") else str(m.role)

    return OrgContext(org_id=org_id, user_id=user_id, role=role)


async def org_scoped_db(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Tuple[OrgContext, AsyncSession]:
    """P5-1 业务 endpoint 标准依赖: 解析 OrgContext + apply_rls_context + 返 (org, db)。"""
    org_ctx = await get_org_context(request)
    await apply_rls_context(db, org_ctx.org_id)
    return org_ctx, db
