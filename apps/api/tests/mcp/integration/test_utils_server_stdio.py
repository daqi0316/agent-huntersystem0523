"""Integration test: 启动真 mcp-utils subprocess，stdio 通信，list_tools + call_tool。

V-5 测试金字塔 integration 层：启动 1 个真 server，验证端到端。
跑法：.venv/bin/python -m pytest tests/mcp/integration/ -v
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# 让 mcp client 可用
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ── 工具函数 ──────────────────────────────────────────────────────────
def _project_root() -> Path:
    """apps/api 根目录。"""
    return Path(__file__).resolve().parents[3]


def _server_command() -> tuple[str, list[str]]:
    """构造启动 mcp-utils 的命令。"""
    venv_python = _project_root() / ".venv" / "bin" / "python"
    return str(venv_python), ["-m", "app.mcp_servers.builtin.utils_server"]


# ── 真实启动 subprocess 测 list_tools ────────────────────────────────
class TestUtilsServerStdio:
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_list_tools_via_stdio(self):
        """启动真 mcp-utils 子进程，调 list_tools 验证 4 个工具。"""
        cmd, args = _server_command()
        params = StdioServerParameters(command=cmd, args=args, cwd=str(_project_root()))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert names == {"greet", "get_current_time", "calculate", "log_operation"}, f"got {names}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_call_greet_via_stdio(self):
        """启动真 mcp-utils 子进程，调 greet 工具。

        FastMCP 1.27 总是把 args 包成 {"arguments": {...}}，所以传 wrapped 形式。
        """
        cmd, args = _server_command()
        params = StdioServerParameters(command=cmd, args=args, cwd=str(_project_root()))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("greet", {"arguments": {"name": "Alice", "language": "en"}})
                text = result.content[0].text
                assert "Alice" in text and "Hello" in text

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_call_calculate_via_stdio(self):
        """启动真 mcp-utils 子进程，调 calculate 工具。"""
        cmd, args = _server_command()
        params = StdioServerParameters(command=cmd, args=args, cwd=str(_project_root()))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("calculate", {"arguments": {"expression": "10*5+1"}})
                text = result.content[0].text
                assert text == "51"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_pydantic_rejects_evil_input(self):
        """Pydantic InputModel 真的拦住了恶意输入。

        实现细节：我们的 wrapped handler 把 Pydantic ValidationError 翻译成
        `{"status": "failed", "error": {"code": "VALIDATION_ERROR", ...}}` dict 返回，
        FastMCP 收到 dict 不抛异常所以 isError=False。验证 text 包含 VALIDATION_ERROR 即可。
        """
        cmd, args = _server_command()
        params = StdioServerParameters(command=cmd, args=args, cwd=str(_project_root()))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("calculate", {"arguments": {"expression": "1; os.system(0)"}})
                text = result.content[0].text
                # 我们的 wrapped handler 把 Pydantic 错误序列化成 JSON
                import json
                err = json.loads(text)
                assert err["status"] == "failed", f"unexpected: {err}"
                assert err["error"]["code"] == "VALIDATION_ERROR"
                # pattern 校验失败原因应包含 input 值
                msg_str = json.dumps(err["error"]["message"], ensure_ascii=False)
                assert "1; os.system(0)" in msg_str or "pattern" in msg_str.lower()
