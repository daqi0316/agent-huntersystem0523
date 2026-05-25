"""Skill 基类。

每个 skill 定义一个或多个 OpenAI function-calling 工具。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable


class Skill(ABC):
    """技能基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """技能唯一标识名。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """技能描述（human-friendly）。"""

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """返回 OpenAI function-calling tool schemas 列表。"""

    @abstractmethod
    def get_handlers(self) -> dict[str, Callable[..., Any]]:
        """返回 {tool_name: async_handler} 映射。"""
