"""mcp-search server — 文档 + 网络搜索（PR-9d Type B-light）。

含 2 工具：
  - search_documents（docs_search_tool.py，in-memory 预置 8 条记录）
  - tavily_search（tavily_search.py，需 TAVILY_API_KEY env）

tavily 工具在 key 缺失时返 error 但 server 启动不受影响（运行时检查）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.docs_search_tool import handlers as docs_handlers
from app.tools.docs_search_tool import tools as docs_tools
from app.tools.tavily_search import handlers as tavily_handlers
from app.tools.tavily_search import tools as tavily_tools

ALL_TOOLS = docs_tools + tavily_tools
ALL_HANDLERS: dict[str, callable] = {}
ALL_HANDLERS.update(docs_handlers)
ALL_HANDLERS.update(tavily_handlers)


@entrypoint("mcp-search", capability="read", version="1.0.0")
def main():
    return ALL_TOOLS, ALL_HANDLERS


if __name__ == "__main__":
    main()
