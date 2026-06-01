"""AgentRegistry — 统一 Agent 注册与发现。

提供全局单例，管理所有 Agent 的名称→实例映射。
支持 lazy registration（__init__ 时自动注册）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.base import BaseAgent


class AgentRegistry:
    """统一 Agent 注册表 — 名称→实例映射。"""

    _agents: dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, name: str, agent: BaseAgent) -> None:
        """注册 Agent 实例。如果名称已存在会覆盖并打印警告。"""
        if name in cls._agents:
            import warnings
            warnings.warn(f"AgentRegistry: 覆盖已注册的 agent '{name}'")
        cls._agents[name] = agent

    @classmethod
    def resolve(cls, name: str) -> BaseAgent | None:
        """根据名称解析 Agent 实例。不存在时返回 None。"""
        return cls._agents.get(name)

    @classmethod
    def list_agents(cls) -> list[str]:
        """列出所有已注册的 Agent 名称。"""
        return list(cls._agents.keys())

    @classmethod
    def get_status(cls, name: str) -> dict[str, Any]:
        """查询指定 Agent 的状态信息。"""
        agent = cls._agents.get(name)
        if agent is None:
            return {"name": name, "registered": False, "error": "not_found"}
        return {
            "name": name,
            "registered": True,
            "type": type(agent).__name__,
            "has_system_prompt": bool(getattr(agent, "system_prompt", None)),
        }

    @classmethod
    def unregister(cls, name: str) -> bool:
        """注销 Agent。返回是否成功。"""
        if name in cls._agents:
            del cls._agents[name]
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """清空注册表（主要用于测试）。"""
        cls._agents.clear()
