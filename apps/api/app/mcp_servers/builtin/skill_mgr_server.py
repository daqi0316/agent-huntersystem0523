"""mcp-skill-mgr server — skill 元操作（PR-9e Type B-light 子进程）。

含 1 工具：
  - install_skill_from_url（skill_tool.py，subprocess.run git clone）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.skill_tool import handlers as skill_handlers
from app.tools.skill_tool import tools as skill_tools


@entrypoint("mcp-skill-mgr", capability="admin", version="1.0.0")
def main():
    return skill_tools, skill_handlers


if __name__ == "__main__":
    main()
