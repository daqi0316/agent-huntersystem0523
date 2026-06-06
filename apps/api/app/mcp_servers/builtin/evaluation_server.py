"""mcp-evaluation server — 评估流（PR-9b Type B 业务服务）。

包含 2 工具：
  - save_evaluation（evaluation.py，PR-9a 已修走 service）
  - generate_evaluation_report（evaluation.py）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.evaluation import handlers as evaluation_handlers
from app.tools.evaluation import tools as evaluation_tools


@entrypoint("mcp-evaluation", capability="write", version="1.0.0")
def main():
    return evaluation_tools, evaluation_handlers


if __name__ == "__main__":
    main()
