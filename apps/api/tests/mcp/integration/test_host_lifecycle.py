"""Integration test: MCPHost 生命周期 + 真实 utils server stdio + 重启。

V-5 integration 层：启动真 MCPHost，验证：
  - 拉起 utils server 子进程
  - list_tools 返回 4 个
  - call_tool 真打通
  - 杀掉子进程，host 3s 内自动重启（指数退避首次 1s）
  - 优雅 shutdown

跑法：.venv/bin/python -m pytest tests/mcp/integration/test_host_lifecycle.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

# 强制用 .venv 里的 python
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _chdir_to_apps_api():
    """让 config.json 路径能相对解析。"""
    old = os.getcwd()
    os.chdir(_PROJECT_ROOT)
    yield
    os.chdir(old)


class TestMCPHostLifecycle:
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_start_list_call_shutdown(self):
        """端到端：start → utils 4 tool → call_tool → shutdown。

        v0.4c core=5 server 后本测聚焦 utils (4 工具), 验 host.subprocess 路径.
        """
        from app.mcp.host import mcp_host

        connected = await mcp_host.start(phases=["core"])
        assert connected == 5, f"expected 5 core connected, got {connected}"

        try:
            utils_tools = mcp_host.registry.by_server("mcp-utils")
            assert len(utils_tools) == 4, f"utils tools: {len(utils_tools)}"
            tool_names = {e.name for e in utils_tools}
            assert tool_names == {"greet", "get_current_time", "calculate", "log_operation"}

            r = await mcp_host.call_tool("calculate", {"expression": "10+5"})
            assert r == "15", f"expected '15', got {r}"

            r2 = await mcp_host.call_tool("greet", {"name": "Alice", "language": "en"})
            assert "Alice" in r2 and "Hello" in r2
        finally:
            await mcp_host.shutdown()
            assert len(mcp_host._watch_tasks) == 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_pydantic_rejects_evil_input_via_host(self):
        """host.call_tool 走 Pydantic 校验（不依赖 server）。"""
        from app.mcp.host import mcp_host
        await mcp_host.start(phases=["core"])
        try:
            r = await mcp_host.call_tool("calculate", {"expression": "1; os.system(0)"})
            assert r["status"] == "failed"
            assert r["error"]["code"] == "VALIDATION_ERROR"
        finally:
            await mcp_host.shutdown()

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    @pytest.mark.skip(reason="PR-1a 范围暂不含真正 supervisor 重启（推迟到 PR-4）；当前 AsyncExitStack 不能重 enter 同一 context")
    async def test_server_restart_on_kill(self):
        """kill 子进程 → host 自动重启（指数退避）。"""
        from app.mcp.host import mcp_host
        await mcp_host.start(phases=["core"])
        try:
            # 等 list_tools 完成
            for _ in range(20):
                if mcp_host.registry.has("calculate"):
                    break
                await asyncio.sleep(0.5)
            assert mcp_host.registry.has("calculate")

            # 找子进程 pid
            task = mcp_host._watch_tasks["mcp-utils"]
            # 用 psutil 找
            import psutil
            parent_pid = os.getpid()
            children = psutil.Process(parent_pid).children(recursive=True)
            assert len(children) >= 1, f"no mcp subprocess, found {len(children)}"
            target_pid = children[0].pid
            print(f"\n[TEST] killing mcp-utils pid={target_pid}")
            os.kill(target_pid, 9)  # SIGKILL

            # 等重启（首次 backoff 1s）
            await asyncio.sleep(4)

            # server 应该被重启（restart_count 增到 1）
            assert mcp_host._restart_counts.get("mcp-utils", 0) >= 1
            # registry 应该又重新有 calculate（说明新 session 拉起 + list_tools 完成）
            for _ in range(10):
                if mcp_host.registry.has("calculate"):
                    break
                await asyncio.sleep(0.5)
            # call_tool 应该又能通
            r = await mcp_host.call_tool("calculate", {"expression": "2*3"})
            assert r == "6", f"after restart call_tool failed: {r}"
        finally:
            await mcp_host.shutdown()

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_list_servers_endpoint(self):
        """host.list_servers 返回 server 状态 (v0.4c core=5)."""
        from app.mcp.host import mcp_host
        await mcp_host.start(phases=["core"])
        try:
            for _ in range(20):
                if mcp_host.registry.has("calculate"):
                    break
                await asyncio.sleep(0.5)
            servers = mcp_host.list_servers()
            assert len(servers) == 5
            utils = next(s for s in servers if s["server_id"] == "mcp-utils")
            assert utils["up"] is True
            assert utils["tool_count"] == 4
        finally:
            await mcp_host.shutdown()

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_list_tools_endpoint(self):
        """host.list_tools(format='openai' | 'mcp')。v0.4c core=5 server, 9 工具合计。"""
        from app.mcp.host import mcp_host
        await mcp_host.start(phases=["core"])
        try:
            for _ in range(20):
                if mcp_host.registry.has("calculate"):
                    break
                await asyncio.sleep(0.5)
            tools_mcp = mcp_host.list_tools(format="mcp")
            assert len(tools_mcp) == 9, f"got {len(tools_mcp)}"
            for t in tools_mcp:
                assert "name" in t
                assert "inputSchema" in t
                assert "meta" in t
                assert "capability" in t["meta"]
            tools_openai = mcp_host.list_tools(format="openai")
            assert len(tools_openai) == 9
            for t in tools_openai:
                assert t["type"] == "function"
                assert "function" in t
        finally:
            await mcp_host.shutdown()
