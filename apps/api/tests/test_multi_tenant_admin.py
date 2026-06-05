"""P5-1 PR 4 单元测试 — admin_db 跨 org 访问。

覆盖:
  - admin engine 独立于 app engine
  - admin 路径 (postgres BYPASSRLS) 可跨 org query
  - app 路径 (airecruit_app) 被 RLS 隔离
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.admin_db import admin_engine as default_admin_engine
from app.core.org_context import apply_rls_context
from app.models.user import UserRole

SUPERUSER_URL = settings.database_url
APP_URL = SUPERUSER_URL.replace(
    "postgresql+asyncpg://postgres:postgres@",
    "postgresql+asyncpg://airecruit_app:app_pw@",
    1,
)


def _admin_engine():
    return create_async_engine(SUPERUSER_URL)


def _app_engine():
    return create_async_engine(APP_URL)


@pytest.mark.asyncio
async def test_admin_engine_can_cross_org_query():
    """postgres (BYPASSRLS) 跨 org 可见所有数据。"""
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    user_a = f"admin-test-a-{uuid.uuid4().hex[:8]}"
    user_b = f"admin-test-b-{uuid.uuid4().hex[:8]}"
    cand_a = str(uuid.uuid4())
    cand_b = str(uuid.uuid4())
    try:
        async with _admin_engine().begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO organization (id, slug, name, plan, status) "
                    "VALUES (:id, :slug, :name, 'starter', 'active')"
                ),
                {"id": org_a, "slug": f"adma-{org_a[:8]}", "name": "AdminTest A"},
            )
            await conn.execute(
                text(
                    "INSERT INTO organization (id, slug, name, plan, status) "
                    "VALUES (:id, :slug, :name, 'starter', 'active')"
                ),
                {"id": org_b, "slug": f"admb-{org_b[:8]}", "name": "AdminTest B"},
            )
            await conn.execute(
                text(
                    "INSERT INTO candidates (id, name, email, skills, status, org_id) "
                    "VALUES (:id, 'a', :email, ARRAY[]::text[], 'active', :oid)"
                ),
                {"id": cand_a, "email": f"{cand_a[:8]}@t.com", "oid": org_a},
            )
            await conn.execute(
                text(
                    "INSERT INTO candidates (id, name, email, skills, status, org_id) "
                    "VALUES (:id, 'b', :email, ARRAY[]::text[], 'active', :oid)"
                ),
                {"id": cand_b, "email": f"{cand_b[:8]}@t.com", "oid": org_b},
            )

        async with _admin_engine().begin() as conn:
            r = await conn.execute(
                text(
                    "SELECT count(*) FROM candidates WHERE org_id IN (:a, :b)"
                ),
                {"a": org_a, "b": org_b},
            )
            assert r.scalar() == 2
    finally:
        async with _admin_engine().begin() as conn:
            await conn.execute(
                text("DELETE FROM candidates WHERE org_id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            )
            await conn.execute(
                text("DELETE FROM organization WHERE id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            )


@pytest.mark.asyncio
async def test_app_engine_cannot_cross_org_with_set():
    """airecruit_app 跨 org query 只能看到 1 个 org。"""
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    cand_a = str(uuid.uuid4())
    cand_b = str(uuid.uuid4())
    try:
        async with _admin_engine().begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO organization (id, slug, name, plan, status) "
                    "VALUES (:id, :slug, :name, 'starter', 'active')"
                ),
                {"id": org_a, "slug": f"appcros-a-{org_a[:8]}", "name": "Cross A"},
            )
            await conn.execute(
                text(
                    "INSERT INTO organization (id, slug, name, plan, status) "
                    "VALUES (:id, :slug, :name, 'starter', 'active')"
                ),
                {"id": org_b, "slug": f"appcros-b-{org_b[:8]}", "name": "Cross B"},
            )
            await conn.execute(
                text(
                    "INSERT INTO candidates (id, name, email, skills, status, org_id) "
                    "VALUES (:id, 'a', :email, ARRAY[]::text[], 'active', :oid)"
                ),
                {"id": cand_a, "email": f"{cand_a[:8]}@c.com", "oid": org_a},
            )
            await conn.execute(
                text(
                    "INSERT INTO candidates (id, name, email, skills, status, org_id) "
                    "VALUES (:id, 'b', :email, ARRAY[]::text[], 'active', :oid)"
                ),
                {"id": cand_b, "email": f"{cand_b[:8]}@c.com", "oid": org_b},
            )

        async with _app_engine().begin() as conn:
            await apply_rls_context(conn, org_a)
            r = await conn.execute(
                text("SELECT count(*) FROM candidates WHERE org_id = :oid"),
                {"oid": org_a},
            )
            cnt_a = r.scalar()
            assert cnt_a == 1, f"airecruit_app 隔离后 org A 应 1 行, 实际 {cnt_a}"

            r = await conn.execute(
                text("SELECT count(*) FROM candidates WHERE org_id = :oid"),
                {"oid": org_b},
            )
            cnt_b = r.scalar()
            assert cnt_b == 0, f"airecruit_app 隔离后 org B 应 0 行 (RLS 拦), 实际 {cnt_b}"
    finally:
        async with _admin_engine().begin() as conn:
            await conn.execute(
                text("DELETE FROM candidates WHERE org_id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            )
            await conn.execute(
                text("DELETE FROM organization WHERE id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            )
