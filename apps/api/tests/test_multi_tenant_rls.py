"""P5-1 PR 2 单元测试 — 15 张业务表加 org_id + RLS 启用验证。

覆盖:
  - 14 张业务表 (candidates/jobs/...) 都有 org_id 列
  - 14 张表都 RLS 启用
  - 14 张表都有 org_isolation policy
  - P0-1 修法: 不 SET LOCAL 时 query 返 default org 数据 (不 500)
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings

EXPECTED_TABLES = [
    "candidates",
    "job_positions",
    "applications",
    "interviews",
    "settings",
    "session_summaries",
    "memory_facts",
    "mcp_servers",
    "conversation_sessions",
    "conversation_messages",
    "recommendations",
    "command_audit_log",
    "approvals",
    "operation_logs",
]

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000000"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(settings.database_url)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def conn(engine):
    async with engine.connect() as c:
        yield c


@pytest.mark.asyncio
async def test_org_id_column_on_all_business_tables(conn):
    r = await conn.execute(
        text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE column_name='org_id' AND table_schema='public' "
            "AND table_name = ANY(:tables) ORDER BY table_name"
        ),
        {"tables": EXPECTED_TABLES},
    )
    rows = r.fetchall()
    found = {row[0] for row in rows}
    assert found == set(EXPECTED_TABLES), f"missing: {set(EXPECTED_TABLES) - found}"


@pytest.mark.asyncio
async def test_rls_enabled_on_all_business_tables(conn):
    r = await conn.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname='public' AND rowsecurity=true "
            "AND tablename = ANY(:tables)"
        ),
        {"tables": EXPECTED_TABLES},
    )
    rows = r.fetchall()
    found = {row[0] for row in rows}
    assert found == set(EXPECTED_TABLES), f"missing RLS: {set(EXPECTED_TABLES) - found}"


@pytest.mark.asyncio
async def test_org_isolation_policy_exists(conn):
    r = await conn.execute(
        text(
            "SELECT tablename FROM pg_policies "
            "WHERE schemaname='public' AND policyname='org_isolation' "
            "AND tablename = ANY(:tables)"
        ),
        {"tables": EXPECTED_TABLES},
    )
    rows = r.fetchall()
    found = {row[0] for row in rows}
    assert found == set(EXPECTED_TABLES), f"missing policy: {set(EXPECTED_TABLES) - found}"


@pytest.mark.asyncio
async def test_p0_1_default_org_fallback_no_set_local(conn):
    """P0-1 修法: 不 SET LOCAL 不 500, 返 default org 数据。"""
    await conn.execute(text("COMMIT"))
    r = await conn.execute(text("SELECT current_setting('app.current_org_id', true)"))
    assert r.scalar() is None
    r2 = await conn.execute(
        text("SELECT 1 FROM candidates WHERE org_id = :oid LIMIT 1"),
        {"oid": DEFAULT_ORG_ID},
    )
    r2.scalar()


@pytest.mark.asyncio
async def test_p0_1_org_isolation_policy_is_valid_sql(conn):
    """policy 必须能被 Postgres parser 接受 + 类型不冲突。"""
    r = await conn.execute(
        text(
            "SELECT pg_get_expr(polqual, polrelid) "
            "FROM pg_policy pol "
            "JOIN pg_class c ON pol.polrelid = c.oid "
            "WHERE pol.polname='org_isolation' AND c.relname='candidates' "
            "LIMIT 1"
        )
    )
    policy_expr = r.scalar()
    assert policy_expr is not None
    assert "::uuid" in policy_expr
    assert "current_setting" in policy_expr
    assert DEFAULT_ORG_ID in policy_expr
