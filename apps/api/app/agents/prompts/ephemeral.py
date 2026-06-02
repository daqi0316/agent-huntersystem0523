"""ephemeral.py — 临时 Prompt 覆盖层。

调试 / A-B 测试时临时替换 Prompt，优先级最高，不缓存。
生产默认禁用（EPHEMERAL_ENABLED=true 才生效）。
"""

import os
from threading import local

_threadlocal = local()


def ephemeral_override(text: str) -> None:
    """设置当前线程的 ephemeral 覆盖文本。

    覆盖后，当前线程的 _load_system_prompt() 返回此文本（assemble 时被注入）。
    不缓存，每次调用 _load_system_prompt 重新读取。
    线程结束时自动清除。

    Args:
        text: 要覆盖的 Prompt 内容（空字符串 = 清除覆盖）
    """
    _threadlocal.ephemeral_text = text


def get_ephemeral_text() -> str:
    """获取当前线程的 ephemeral 覆盖文本。"""
    return getattr(_threadlocal, "ephemeral_text", "")


def clear_ephemeral() -> None:
    """清除当前线程的 ephemeral 覆盖。"""
    _threadlocal.ephemeral_text = ""


def is_ephemeral_enabled() -> bool:
    """检查 ephemeral 层是否启用（ENV flag）。"""
    return os.getenv("EPHEMERAL_ENABLED", "false").lower() == "true"
