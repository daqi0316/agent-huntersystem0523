"""System Prompt 加载器。

所有 Prompt 放在 prompts/ 目录下作为独立 .md 文件，
不再硬编码在 Python 类中。
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

_PROMPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """从文件加载 System Prompt。不存在时返回空字符串。

    Args:
        name: Prompt 文件名（不含 .md 后缀）

    Returns:
        Prompt 内容字符串，不存在时返回 ""
    """
    if name in _CACHE:
        return _CACHE[name]

    filepath = os.path.join(_PROMPT_DIR, f"{name}.md")
    if not os.path.exists(filepath):
        logger.warning("System prompt file not found: %s", filepath)
        return ""

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        _CACHE[name] = content
        return content
    except Exception as e:
        logger.warning("Failed to load prompt '%s': %s", name, e)
        return ""


def reload_prompts() -> None:
    """清空缓存，下次 load_prompt 会重新读取文件（开发模式热加载）。"""
    _CACHE.clear()
    logger.info("System prompt cache cleared")


def get_available_prompts() -> list[str]:
    """列出所有可用的 Prompt 名称（不含 .md 后缀）。"""
    files = []
    for f in os.listdir(_PROMPT_DIR):
        if f.endswith(".md"):
            files.append(f[:-3])
    return sorted(files)
