"""Local conftest for test_commands — 隔离父 conftest 的 langgraph 依赖.

父 conftest (tests/conftest.py) 会 import app.main, 进而拉入 langgraph 全家桶
(可能含 torch / transformers, 几 GB). V.1 命令测试不依赖这些.

使用方式:
    cd apps/api
    .venv/bin/python -m pytest --confcutdir=tests/test_commands tests/test_commands/

本 conftest 只提供 V.1 需要的最小 fixture.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop per session to keep async fixtures alive."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def mock_db_session():
    """通用 AsyncMock, 用于 audit / executor 测试."""
    from unittest.mock import AsyncMock, MagicMock
    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    return db
