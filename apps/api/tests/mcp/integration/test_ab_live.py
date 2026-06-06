"""Integration test: 启动 MCPHost + agent_service 接入，验证 AB 包装生效。

跑法：.venv/bin/python -m pytest tests/mcp/integration/test_ab_live.py -v
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _chdir():
    old = os.getcwd()
    os.chdir(_PROJECT_ROOT)
    yield
    os.chdir(old)


class TestABLive:
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_host_started_calculate_gets_ab_wrapped(self):
        """启动 MCPHost → agent_service._get_handlers 把 calculate wrap 成 AB router。"""
        from app.mcp.host import mcp_host
        from app.mcp import ab_router as _ab_mod
        from app.mcp.ab_router import get_config, update_percent

        # 重置 AB config（不让测试间污染）
        _ab_mod._config = _ab_mod.ABConfig(enabled=False, percent=0, allowlist=())

        await mcp_host.start(phases=["core"])
        try:
            # 等 utils server 连上 + session 建好
            for _ in range(30):
                if mcp_host.registry.has("calculate") and mcp_host._sessions:
                    break
                await asyncio.sleep(0.5)
            assert mcp_host.registry.has("calculate"), "registry missing calculate"
            assert mcp_host._sessions, f"no sessions: {list(mcp_host._sessions.keys())}"

            # 重新跑 _register_builtins（如果有 lazy init）
            from app.services.agent_service import (
                _register_builtins, _get_handlers,
            )
            await _register_builtins()
            handlers = _get_handlers()
            h = handlers["calculate"]
            assert h is not None

            # AB router 总是 wrap（hot-reload 要求 config 改了立即生效）
            # 不管 enabled 与否，wrap name 永远是 ab_wrapped_*
            assert "ab_wrapped" in str(h.__name__), f"expected AB wrap, got {h.__name__}"

            # 但 disabled 时调 → 仍走 old path（router 内部决策）
            assert not get_config().enabled
            r = await h(expression="3+4")
            assert r == "7", f"disabled AB should go old path, got {r!r}"

            # 启用 AB（100% 走 new path）
            update_percent(100, enabled=True)
            r = await h(expression="7*8")
            assert r == "56", f"enabled AB 100% should go new path, got {r!r}"
        finally:
            # 恢复 AB disabled + 关 host
            try:
                update_percent(0, enabled=False)
            except NameError:
                pass  # 早期 import 失败
            await mcp_host.shutdown()
