"""mcp-dashboard server — 看板 + 面试日程调度（PR-9f Type B 调度）。

含 3 工具：
  - get_dashboard_stats（dashboard.py，3 个 COUNT(*) 聚合）
  - get_upcoming_interviews（schedule_tool.py，未来 n 天面试）
  - get_schedule（schedule_tool.py，指定月份面试，含 past/future 计数）

调度类工具（无写操作），capability=read。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.dashboard import handlers as dashboard_handlers
from app.tools.dashboard import tools as dashboard_tools
from app.tools.schedule_tool import handlers as schedule_handlers
from app.tools.schedule_tool import tools as schedule_tools

ALL_TOOLS = dashboard_tools + schedule_tools
ALL_HANDLERS: dict[str, callable] = {}
ALL_HANDLERS.update(dashboard_handlers)
ALL_HANDLERS.update(schedule_handlers)


@entrypoint("mcp-dashboard", capability="read", version="1.0.0")
def main():
    return ALL_TOOLS, ALL_HANDLERS


if __name__ == "__main__":
    main()
