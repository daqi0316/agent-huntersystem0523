"""Core prompts — 已迁移到模板文件 (agents/prompts/system.md).

所有系统级提示词存储在 agents/prompts/ 目录下的 .md 文件中，
不再硬编码在 Python 代码里。
"""

from __future__ import annotations

from app.agents.prompts import load_prompt


def load_system_prompt() -> str:
    """从模板库加载系统提示词（agents/prompts/system.md）。

    支持热加载：修改 system.md 后，下次调用自动生效。
    开发模式下可调用 reload_prompts() 清空缓存强制重读。
    """
    return load_prompt("system")


# 向后兼容：现有代码（ContextBuilder、agent_service 等）还在引用 SYSTEM_PROMPT 常量
SYSTEM_PROMPT = load_system_prompt()