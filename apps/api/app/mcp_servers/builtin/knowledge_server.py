"""mcp-knowledge server — RAG 问答（PR-9c Type B LLM）。

仅含 1 工具：
  - search_knowledge（knowledge.py，LLM 调 KnowledgeService.query）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.knowledge import handlers as knowledge_handlers
from app.tools.knowledge import tools as knowledge_tools


@entrypoint("mcp-knowledge", capability="read", version="1.0.0")
def main():
    return knowledge_tools, knowledge_handlers


if __name__ == "__main__":
    main()
