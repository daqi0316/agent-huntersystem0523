"""pytest fixtures: FastAPI test client + singleton cleanup."""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import engine


@pytest.fixture(autouse=True)
def _clear_agent_registry():
    """Clear AgentRegistry before each test to prevent singleton state leaking."""
    from app.agents.registry import AgentRegistry
    AgentRegistry.clear()
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
    boundaries."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await engine.dispose()
