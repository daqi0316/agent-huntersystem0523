"""P5-1 PR 3 — auto_create_default_org 中间件 (P0-5 E2E 透明)。"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models import Membership, MembershipRole, MembershipStatus, Organization, OrganizationPlan, OrganizationStatus
from app.models.user import User


async def get_or_create_default_org(user_id: str) -> str:
    """用户无任何 membership 时, 自动建 default org + 加 owner。

    P0-5 修法: E2E 透明, 不需要预先建 org。
    P5-1 阶段开启, Phase 6 后关闭 (真实客户走邀请流程)。
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            r = await session.execute(
                select(Membership).where(
                    Membership.user_id == user_id,
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
            m = r.scalar_one_or_none()
            if m is not None:
                return m.org_id

            r2 = await session.execute(select(User).where(User.id == user_id))
            user = r2.scalar_one_or_none()
            if user is None:
                raise HTTPException(401, "user not found")

            slug = f"personal-{user_id}"
            org = Organization(
                id=str(uuid.uuid4()),
                slug=slug,
                name=f"{user.name} 的工作区",
                plan=OrganizationPlan.STARTER,
                status=OrganizationStatus.ACTIVE,
            )
            session.add(org)
            await session.flush()

            membership = Membership(
                org_id=org.id,
                user_id=user_id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
            session.add(membership)
        return org.id
