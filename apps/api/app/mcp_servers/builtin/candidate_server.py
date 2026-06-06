"""mcp-candidate server — 候选人 CRUD + 搜索（PR-9b Type B 业务服务）。

包含 5 工具：
  - create_candidate / update_candidate / archive_candidate（candidate.py）
  - search_candidates / get_candidate_detail（candidate_search.py）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.candidate import handlers as candidate_handlers
from app.tools.candidate import tools as candidate_tools
from app.tools.candidate_search import handlers as search_handlers
from app.tools.candidate_search import tools as search_tools

ALL_TOOLS = candidate_tools + search_tools
ALL_HANDLERS: dict[str, callable] = {}
ALL_HANDLERS.update(candidate_handlers)
ALL_HANDLERS.update(search_handlers)


@entrypoint("mcp-candidate", capability="write", version="1.0.0")
def main():
    return ALL_TOOLS, ALL_HANDLERS


if __name__ == "__main__":
    main()
