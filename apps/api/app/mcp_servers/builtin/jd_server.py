"""mcp-jd server — JD 生成（PR-9c Type B LLM）。

仅含 1 工具：
  - generate_jd（jd.py，直接 LLM chat，无 service 抽象）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.jd import handlers as jd_handlers
from app.tools.jd import tools as jd_tools


@entrypoint("mcp-jd", capability="write", version="1.0.0")
def main():
    return jd_tools, jd_handlers


if __name__ == "__main__":
    main()
