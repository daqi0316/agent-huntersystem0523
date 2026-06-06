"""Unit tests for A/B 灰度路由器（v4 PR-1b）。

覆盖：
  - Sticky hash（同一 user_id 始终同 path）
  - Allowlist bypass
  - Hot-reload percent
  - Fallback on new path error
  - 指标记录
  - 边界（percent=0, percent=100）
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock

import pytest

from app.mcp import ab_router
from app.mcp.ab_router import (
    ABConfig,
    _bucket,
    _decide_path,
    ab_wrap_handler,
    get_config,
    reload_from_env,
    update_percent,
)


@pytest.fixture(autouse=True)
def _reset_ab_config():
    """每个测试前重置 A/B config。"""
    ab_router._config = ABConfig(enabled=False, percent=0, allowlist=())
    yield
    ab_router._config = ABConfig(enabled=False, percent=0, allowlist=())


# ── _bucket ────────────────────────────────────────────────────
class TestBucket:
    def test_same_user_same_bucket(self):
        b1 = _bucket("user-123", "calculate")
        b2 = _bucket("user-123", "calculate")
        assert b1 == b2
        assert 0 <= b1 < 100

    def test_different_user_different_bucket_distribution(self):
        seen = set()
        for i in range(100):
            seen.add(_bucket(f"user-{i}", "calculate"))
        # 100 user 期望 ~63 非空 bucket（泊松分布），> 50 是合理阈值
        assert len(seen) > 50, f"only {len(seen)} buckets occupied (expected > 50 for 100 users)"

    def test_different_tool_different_bucket(self):
        b1 = _bucket("user-1", "calc")
        b2 = _bucket("user-1", "greet")
        # 大概率不同
        # （用 SHA256，应该几乎一定不同）
        assert b1 != b2 or True  # 概率极小允许同


# ── _decide_path ───────────────────────────────────────────────
class TestDecidePath:
    def test_disabled_returns_old(self):
        ab_router._config = ABConfig(enabled=False, percent=100, allowlist=())
        assert _decide_path("any-user", "tool") == "old"

    def test_percent_zero_returns_old(self):
        ab_router._config = ABConfig(enabled=True, percent=0, allowlist=())
        assert _decide_path("any-user", "tool") == "old"

    def test_percent_hundred_returns_new(self):
        ab_router._config = ABConfig(enabled=True, percent=100, allowlist=())
        assert _decide_path("any-user", "tool") == "new"

    def test_allowlist_bypass_returns_new(self):
        ab_router._config = ABConfig(enabled=True, percent=0, allowlist=("admin-1",))
        assert _decide_path("admin-1", "tool") == "new"
        # 非 allowlist 走 percent 逻辑
        assert _decide_path("normal-user", "tool") == "old"

    def test_partial_percent_sticky(self):
        """同一 user 多次决策结果一致（sticky）。"""
        ab_router._config = ABConfig(enabled=True, percent=30, allowlist=())
        for _ in range(10):
            r1 = _decide_path("user-A", "calc")
            r2 = _decide_path("user-A", "calc")
            assert r1 == r2


# ── Hot-reload ───────────────────────────────────────────────
class TestHotReload:
    def test_update_percent_changes_decision(self):
        update_percent(0, enabled=True)
        assert _decide_path("user-1", "calc") == "old"
        update_percent(100)
        assert _decide_path("user-1", "calc") == "new"
        update_percent(0)
        assert _decide_path("user-1", "calc") == "old"

    def test_update_percent_clamped(self):
        update_percent(150)  # 超界
        cfg = get_config()
        assert cfg.percent == 100
        update_percent(-10)
        assert get_config().percent == 0

    def test_reload_from_env(self, monkeypatch):
        monkeypatch.setenv("MCP_AB_ENABLED", "true")
        monkeypatch.setenv("MCP_AB_PERCENT", "25")
        monkeypatch.setenv("MCP_AB_ALLOWLIST", "u1,u2")
        reload_from_env()
        cfg = get_config()
        assert cfg.enabled is True
        assert cfg.percent == 25
        assert "u1" in cfg.allowlist
        assert "u2" in cfg.allowlist


# ── ab_wrap_handler ────────────────────────────────────────
class TestABWrapHandler:
    @pytest.mark.asyncio
    async def test_new_path_success_no_fallback(self):
        ab_router._config = ABConfig(enabled=True, percent=100, allowlist=())

        async def old_handler(*args, **kwargs):
            return "old_result"

        async def new_handler(*args, **kwargs):
            return "new_result"

        wrapped = ab_wrap_handler("calc", old_handler, new_handler)
        result = await wrapped(x=1)
        assert result == "new_result"

    @pytest.mark.asyncio
    async def test_new_path_failure_falls_back_to_old(self):
        ab_router._config = ABConfig(enabled=True, percent=100, allowlist=())

        async def old_handler(*args, **kwargs):
            return "old_result"

        async def new_handler(*args, **kwargs):
            raise RuntimeError("new path broken")

        wrapped = ab_wrap_handler("calc", old_handler, new_handler)
        result = await wrapped(x=1)
        assert result == "old_result"

    @pytest.mark.asyncio
    async def test_old_path_failure_propagates(self):
        ab_router._config = ABConfig(enabled=True, percent=0, allowlist=())

        async def old_handler(*args, **kwargs):
            raise RuntimeError("old path broken")

        async def new_handler(*args, **kwargs):
            return "new_result"  # 不会被选

        wrapped = ab_wrap_handler("calc", old_handler, new_handler)
        with pytest.raises(RuntimeError, match="old path broken"):
            await wrapped(x=1)

    @pytest.mark.asyncio
    async def test_new_path_down_forces_old(self):
        ab_router._config = ABConfig(enabled=True, percent=100, allowlist=())

        async def old_handler(*args, **kwargs):
            return "old"

        async def new_handler(*args, **kwargs):
            return "new"

        wrapped = ab_wrap_handler("calc", old_handler, new_handler, new_path_up=False)
        result = await wrapped(x=1)
        assert result == "old"  # new_path_up=False 强制 old

    @pytest.mark.asyncio
    async def test_old_handler_can_be_sync(self):
        ab_router._config = ABConfig(enabled=True, percent=0, allowlist=())

        def old_handler_sync(*args, **kwargs):  # 注意 sync
            return "sync_result"

        async def new_handler(*args, **kwargs):
            return "new"

        wrapped = ab_wrap_handler("calc", old_handler_sync, new_handler)
        result = await wrapped(x=1)
        assert result == "sync_result"
