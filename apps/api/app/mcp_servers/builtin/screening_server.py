"""mcp-screening server — AI 简历筛选（PR-9c Type B LLM）。

仅含 1 工具：
  - screen_resume（screening.py，LLM 调 ScreeningService.screen_resume）

重名工具（search_candidates / get_candidate）留在 screening.py 中，
PR-9g 合并到 candidate_search 后从本 server 剔除。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.screening import handlers as screening_handlers
from app.tools.screening import tools as screening_tools

ALL_TOOLS = [t for t in screening_tools if t["function"]["name"] == "screen_resume"]
ALL_HANDLERS: dict[str, callable] = {"screen_resume": screening_handlers["screen_resume"]}


@entrypoint("mcp-screening", capability="write", version="1.0.0")
def main():
    return ALL_TOOLS, ALL_HANDLERS


if __name__ == "__main__":
    main()
