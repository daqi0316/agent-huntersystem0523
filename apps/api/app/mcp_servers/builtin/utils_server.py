"""mcp-utils server — 首个 MCP server 示范（4 工具）。

包含：
  - greet: 个性化问候
  - get_current_time: 时区感知时间
  - calculate: 安全数学表达式
  - log_operation: 审计日志（DB 写入）

启动方式（stdio）：
  cd apps/api && .venv/bin/python -m app.mcp_servers.builtin.utils_server

Host 连入（FastMCP client）：
  from mcp import ClientSession, StdioServerParameters
  from mcp.client.stdio import stdio_client

  params = StdioServerParameters(command=".venv/bin/python", args=["-m", "app.mcp_servers.builtin.utils_server"])
  async with stdio_client(params) as (read, write):
      session = ClientSession(read, write)
      await session.initialize()
      tools = await session.list_tools()
      result = await session.call_tool("greet", {"name": "Alice"})
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 允许 `python -m app.mcp_servers.builtin.utils_server` 启动
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint, run_stdio_server  # noqa: E402
from app.tools.calc_tool import handlers as calc_handlers  # noqa: E402
from app.tools.calc_tool import tools as calc_tools  # noqa: E402
from app.tools.greet_tool import handlers as greet_handlers  # noqa: E402
from app.tools.greet_tool import tools as greet_tools  # noqa: E402
from app.tools.operation_log import handlers as log_handlers  # noqa: E402
from app.tools.operation_log import tools as log_tools  # noqa: E402
from app.tools.time_tool import handlers as time_handlers  # noqa: E402
from app.tools.time_tool import tools as time_tools  # noqa: E402


# ── 合并所有 utils 工具 ──────────────────────────────────────────────────
ALL_TOOLS = greet_tools + time_tools + calc_tools + log_tools
ALL_HANDLERS: dict[str, callable] = {}
ALL_HANDLERS.update(greet_handlers)
ALL_HANDLERS.update(time_handlers)
ALL_HANDLERS.update(calc_handlers)
ALL_HANDLERS.update(log_handlers)


@entrypoint("mcp-utils", capability="read", version="1.0.0")
def main():
    """mcp-utils 入口：返回 (tools, handlers) 给框架。"""
    return ALL_TOOLS, ALL_HANDLERS


if __name__ == "__main__":
    main()
