"""pytest fixtures: FastAPI test client + singleton cleanup."""

import asyncio

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import engine


@pytest.fixture(autouse=True)
def _clear_agent_registry():
    """Clear AgentRegistry before each test to prevent singleton state leaking."""
    from app.agents.registry import AgentRegistry
    AgentRegistry.clear()
    yield


@pytest.fixture(autouse=True)
def _reset_mcp_host():
    """重置 mcp_host module-level singleton 状态, 防跨 event loop 状态污染.

    Phase A 推后 (2): ``asyncio_default_fixture_loop_scope=function`` 让每个
    测试新 event loop, 但 module-level ``mcp_host._started=True`` 等 state
    留旧 loop — 旧 task 在旧 loop 死时还在跑, 跟新测试的 start() 冲突.
    修法: 每测前同步清 state 字段 (不 await 旧 task, 跨 loop 不可靠).
    原 4 测 test_host_lifecycle.py 标 skip (Fix-1 ship report §3.3 推后) 现可跑.
    """
    from app.mcp.host import mcp_host
    from app.mcp.registry import ToolRegistry

    mcp_host._watch_tasks.clear()
    mcp_host._sessions.clear()
    mcp_host._pids.clear()
    mcp_host._configs.clear()
    mcp_host._restart_counts.clear()
    mcp_host._exit_stack = None
    mcp_host._started = False
    mcp_host._shutdown = False
    mcp_host.registry = ToolRegistry()
    yield


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop per session to keep asyncpg connections alive."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    """FastAPI test client. Disposes the engine after each test so the
    connection pool does not hold stale connections across event-loop
    boundaries.

    Auth override: P5-1 改造后业务 endpoint 走 `org_scoped_db` dep
    (读 JWT → 查 Membership → apply_rls_context)。 测试不需要真鉴权,
    override `get_current_user_id` + `org_scoped_db` 返回固定 OrgContext +
    真实 DB session, 让 endpoint 拿到 (org_ctx, db) 但跳过 JWT/Membership 流程。
    """
    from app.core.dependencies import get_current_user_id
    from app.core.org_context import org_scoped_db, OrgContext
    from app.core.database import get_db

    async def _mock_user_id() -> str:
        return "test-user-id"

    async def _mock_org_scoped_db(db = Depends(get_db)):
        """Yield (OrgContext, DB session) — skip JWT + Membership lookup.

        Key: `db = Depends(get_db)` 让 FastAPI DI 解析 get_db,
        这样 test 设的 `app.dependency_overrides[get_db]` 才生效。
        之前直接调 `get_db()` 绕过 DI,拿到的是真 DB session。
        """
        org_ctx = OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr")
        yield org_ctx, db

    app.dependency_overrides[get_current_user_id] = _mock_user_id
    app.dependency_overrides[org_scoped_db] = _mock_org_scoped_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)
        app.dependency_overrides.pop(org_scoped_db, None)
        await engine.dispose()
