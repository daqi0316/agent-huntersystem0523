"""Sourcing Tool 基类 — 所有外部招聘平台搜索工具的基础抽象。

每个 SourcingTool 定义:
  - tool schema (OpenAI function-calling format)
  - async handler

设计原则:
  - 无状态：不持有 session/connection，每次调用新建
  - 可扩展：新平台只需继承 + 实现 _execute
  - 安全：禁内部薪酬/敏感数据访问
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class SourcingTool(Protocol):
    """Sourcing 工具协议 — 定义工具的能力边界。"""

    @property
    def tool_schema(self) -> dict:
        """OpenAI function-calling tool schema。"""
        ...

    async def execute(self, **kwargs) -> dict:
        """执行工具，返回标准化结果。

        返回格式:
          {"success": True, "results": [...], "summary": "..."}
          {"success": False, "error": "...", "results": []}
        """
        ...


# ── 标准化结果格式 ──


def success_result(
    results: list[dict],
    summary: str = "",
    platform: str = "",
) -> dict:
    """构造成功的标准化结果。"""
    return {
        "success": True,
        "results": results,
        "summary": summary or f"在 {platform} 找到 {len(results)} 个结果",
        "platform": platform,
        "total": len(results),
    }


def error_result(error: str, platform: str = "") -> dict:
    """构造失败的标准化结果。"""
    return {
        "success": False,
        "results": [],
        "error": error,
        "summary": error,
        "platform": platform,
        "total": 0,
    }
