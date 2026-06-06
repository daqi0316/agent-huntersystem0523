"""mcp-application server — 申请流（PR-9b Type B 业务服务）。

包含 2 工具：
  - create_application / update_application_status（application.py）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.application import handlers as application_handlers
from app.tools.application import tools as application_tools


@entrypoint("mcp-application", capability="write", version="1.0.0")
def main():
    return application_tools, application_handlers


if __name__ == "__main__":
    main()
