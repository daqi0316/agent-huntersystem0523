"""mcp-resume server — 简历解析（PR-9c Type B LLM Bheavy）。

含 3 工具：
  - parse_resume（Bheavy：file 下载 + LLM extract + CandidateService.create）
  - batch_parse_resumes（Bheavy：循环 + 错误聚合）
  - get_candidate_profile（B 读：聚合画像）

事务边界设计：parse_resume 先落 raw_text，再异步调 LLM；批处理分块
提交避免单条失败拖垮整批（PR-9c 计划注：Bheavy 需独立 PR，事务边界
具体设计推到后续，本 server 阶段保留 raw error 透传）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.resume_parser import handlers as resume_handlers
from app.tools.resume_parser import tools as resume_tools


@entrypoint("mcp-resume", capability="write", version="1.0.0")
def main():
    return resume_tools, resume_handlers


if __name__ == "__main__":
    main()
