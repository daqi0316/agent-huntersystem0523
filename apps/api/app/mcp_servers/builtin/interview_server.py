"""mcp-interview server — 面试流（PR-9b Type B 业务服务）。

包含 7 工具：
  - schedule_interview / cancel_interview / record_feedback（interview.py，PR-9a 已修）
  - reschedule_interview / complete_interview / get_interview_detail（interview_extended.py，PR-9a 已修）
  - get_evaluations（screening.py，过渡，PR-9g 重命名后归位）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.interview import handlers as interview_handlers
from app.tools.interview import tools as interview_tools
from app.tools.interview_extended import handlers as extended_handlers
from app.tools.interview_extended import tools as extended_tools
from app.tools.screening import handlers as screening_handlers
from app.tools.screening import tools as screening_tools

ALL_TOOLS = (
    interview_tools
    + extended_tools
    + [t for t in screening_tools if t["function"]["name"] == "get_evaluations"]
)
ALL_HANDLERS: dict[str, callable] = {}
ALL_HANDLERS.update(interview_handlers)
ALL_HANDLERS.update(extended_handlers)
ALL_HANDLERS["get_evaluations"] = screening_handlers["get_evaluations"]


@entrypoint("mcp-interview", capability="write", version="1.0.0")
def main():
    return ALL_TOOLS, ALL_HANDLERS


if __name__ == "__main__":
    main()
