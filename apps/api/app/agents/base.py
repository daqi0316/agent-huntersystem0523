"""所有 Agent 的抽象基类。

提供:
- 自动 System Prompt 加载（从 prompts/ 目录）
- 自动 AgentRegistry 注册（__init_subclass__）
- agent_type 自动推导
"""

from __future__ import annotations

import abc
import logging
import os
import time
from typing import Any

from app.agents.prompts import load_prompt

logger = logging.getLogger(__name__)

ENABLE_LAYERED_PROMPT = os.getenv("ENABLE_LAYERED_PROMPT", "false").lower() == "true"


class BaseAgent(abc.ABC):
    """所有 Agent 的抽象基类。

    统一输出协议:
      每个 Agent 的 run() 必须返回以下格式:
      {
          "agent": str,         # Agent 名称
          "status": str,        # "completed" | "failed" | "rejected"
          "summary": str,       # 一句话摘要
          "result": dict,       # 结构化数据（含 output_keys 对应字段）
          "details": dict,      # 详细数据（可选）
      }

    子类通过 output_keys 声明向 shared_context 暴露的字段。
    """

    # Agent 声明输出到 shared_context 的字段名
    # Orchestrator 会按 "{agent_type}.{key}" 命名空间自动存储
    output_keys: list[str] = []

    def __init__(self, name: str | None = None):
        self.name = name or self._derive_name()
        self._agent_type: str = self._derive_agent_type()
        self._system_prompt: str = ""

        # 自动注册到 AgentRegistry
        try:
            from app.agents.registry import AgentRegistry

            AgentRegistry.register(self.name, self)
        except ImportError:
            pass

    @property
    def agent_type(self) -> str:
        """返回 Agent 类型名称（类名去掉 'Agent' 后缀的小写形式）。"""
        return self._agent_type

    def _operation_id(self) -> str:
        """返回当前操作的 operation_id（由 _record_operation_start 设置）。"""
        return getattr(self, "_current_op_id", "")

    async def _record_operation_start(
        self,
        action: str = "",
        input_summary: str = "",
        user_id: str = "",
    ) -> str:
        """创建操作记录并返回 operation_id。"""
        try:
            from app.services.operation_service import OperationService
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                svc = OperationService(db)
                op = await svc.create(
                    user_id=user_id, agent_name=self.name,
                    action=action, input_summary=input_summary,
                )
                if op:
                    await svc.transition(op.id, "running")
                    self._current_op_id = op.id
                    return op.id
        except Exception as e:
            logger.warning("Failed to record operation start: %s", e)
        return ""

    async def _record_operation_end(
        self,
        operation_id: str = "",
        output_summary: str = "",
        error: str = "",
        success: bool = True,
    ) -> None:
        """完成或失败一条操作记录。"""
        if not operation_id:
            return
        try:
            from app.services.operation_service import OperationService
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                svc = OperationService(db)
                if success:
                    await svc.complete(operation_id, output_summary=output_summary)
                else:
                    await svc.fail(operation_id, error_message=error)
        except Exception as e:
            logger.warning("Failed to record operation end: %s", e)

    @property
    def system_prompt(self) -> str:
        """获取 System Prompt。如果未加载则自动加载。"""
        if not self._system_prompt:
            self._system_prompt = self._load_system_prompt()
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        """手动设置 System Prompt（覆盖文件加载）。"""
        self._system_prompt = value

    @abc.abstractmethod
    async def run(self, input_data: dict) -> dict:
        """执行 Agent 逻辑。

        必须返回统一格式:
        {
            "agent": str,     # self.name
            "status": str,    # "completed" | "failed" | "rejected"
            "summary": str,   # 一句话摘要
            "result": dict,   # 结构化数据（含 output_keys 对应字段）
            "details": dict,  # 详细数据（可选）
        }
        """
        ...

    # ── 统一输出格式 ──

    def format_result(
        self,
        status: str,
        result: dict,
        summary: str = "",
        details: dict | None = None,
    ) -> dict:
        """构造统一输出格式。"""
        return {
            "agent": self.name,
            "status": status,
            "summary": summary,
            "result": result,
            "details": details or {},
        }

    # ── 内部方法 ──

    def _derive_name(self) -> str:
        """从类名推导默认名称。例: ScreeningAgent → screening"""
        name = type(self).__name__
        if name.endswith("Agent"):
            name = name[:-5]
        return name[0].lower() + name[1:] if name else "unknown"

    def _derive_agent_type(self) -> str:
        """从类名推导 Agent 类型。"""
        return self._derive_name()

    def _load_system_prompt(self) -> str:
        """从 prompts/ 目录加载对应的 System Prompt。

        v1 支持两种模式（env flag 控制）:
        - ENABLE_LAYERED_PROMPT=false（默认）: 仅加载该 Agent 自己的 .md（向后兼容）
        - ENABLE_LAYERED_PROMPT=true: 使用 6 层组装（SOUL + MEMORY + USER + AGENT + SAFETY + ENV）
        """
        prompt_name = self._derive_name()

        if not ENABLE_LAYERED_PROMPT:
            content = load_prompt(prompt_name)
            if content:
                logger.debug("Loaded legacy system prompt for '%s' (%d chars)", self.name, len(content))
            else:
                logger.debug("No system prompt file for '%s', using empty", self.name)
            return content

        from app.agents.prompts.prompt_builder import build_layered_prompt, assemble

        user_id = getattr(self, "_user_id", "default") or "default"
        context = {"time": time.strftime("%Y-%m-%d %H:%M:%S")}
        bundle = build_layered_prompt(
            user_id=user_id,
            active_agent=prompt_name,
            context=context,
        )
        content = assemble(bundle)
        logger.debug(
            "Loaded layered system prompt for '%s' (user=%s, %d chars)",
            self.name, user_id, len(content),
        )
        return content
