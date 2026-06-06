"""mcp-job server — 职位 CRUD（PR-9b Type B 业务服务）。

包含 4 工具：
  - create_job / update_job / close_job（job.py）
  - list_jobs（screening.py，过渡，PR-9g 重名合并后归位）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.job import handlers as job_handlers
from app.tools.job import tools as job_tools
from app.tools.screening import handlers as screening_handlers
from app.tools.screening import tools as screening_tools

ALL_TOOLS = job_tools + [t for t in screening_tools if t["function"]["name"] == "list_jobs"]
ALL_HANDLERS: dict[str, callable] = {
    "create_job": job_handlers["create_job"],
    "update_job": job_handlers["update_job"],
    "close_job": job_handlers["close_job"],
    "list_jobs": screening_handlers["list_jobs"],
}


@entrypoint("mcp-job", capability="write", version="1.0.0")
def main():
    return ALL_TOOLS, ALL_HANDLERS


if __name__ == "__main__":
    main()
