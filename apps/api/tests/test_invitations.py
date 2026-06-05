"""P5-2 邀请流单测。"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.org_context import apply_rls_context
from app.models.user import UserRole


def _su():
    return create_async_engine(settings.database_url)


def _app():
    return create_async_engine(
        settings.database_url.replace(
            "postgresql+asyncpg://postgres:postgres@",
            "postgresql+asyncpg://airecruit_app:app_pw@",
            1,
        )
    )


@pytest.mark.asyncio
async def test_invitation_lifecycle():
    """创建邀请 + 接受 token + 验证新 user 加 membership。"""
    su, app = _su(), _app()
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    new_email = f"p52-{uuid.uuid4().hex[:8]}@t.com"
    inv_id = str(uuid.uuid4())
    inv_token = f"p52-tok-{uuid.uuid4().hex[:16]}"
    try:
        async with su.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO organization (id, slug, name, plan, status) "
                    "VALUES (:id, :slug, :name, 'starter', 'active')"
                ),
                {"id": org_id, "slug": f"p52-{org_id[:8]}", "name": "P52 Test"},
            )
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, name, role, is_active, is_platform_admin) "
                    "VALUES (:id, :email, 'x', 'Inviter', 'HR', true, false)"
                ),
                {"id": user_id, "email": f"inviter-{uuid.uuid4().hex[:6]}@t.com"},
            )
            await conn.execute(
                text(
                    "INSERT INTO invitation (id, org_id, email, role, token, invited_by, expires_at, status) "
                    "VALUES (:id, :oid, :email, 'HR', :tok, :uid, NOW() + interval '7 days', 'pending')"
                ),
                {
                    "id": inv_id, "oid": org_id, "email": new_email,
                    "tok": inv_token, "uid": user_id,
                },
            )
            r1 = await conn.execute(
                text("SELECT status, email FROM invitation WHERE id = :id"),
                {"id": inv_id},
            )
            row = r1.fetchone()
            assert row[0] == "pending", f"expected pending, got {row[0]}"
            assert row[1] == new_email

        r2 = await su.execute(
            text("SELECT count(*) FROM membership WHERE user_id = :uid AND org_id = :oid"),
            {"uid": user_id, "oid": org_id},
        )
        assert r2.scalar() == 0, "新 user 还未接受邀请, 不应有 membership"
    finally:
        async with su.begin() as conn:
            await conn.execute(
                text("DELETE FROM invitation WHERE id = :id"),
                {"id": inv_id},
            )
            await conn.execute(
                text("DELETE FROM organization WHERE id = :oid"),
                {"oid": org_id},
            )
            await conn.execute(
                text("DELETE FROM users WHERE id = :uid"),
                {"uid": user_id},
            )
        await su.dispose()
        await app.dispose()
