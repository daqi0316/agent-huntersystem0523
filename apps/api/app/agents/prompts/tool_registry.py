"""tool_registry.py — LLM 工具注册表。

将 skill 暴露为 LLM 可调用的 function-calling tool。
v2 接入 base.py::LLM_AVAILABLE_TOOLS，LLM 通过 load_skill(name) 按需拉取技能内容。
"""

from dataclasses import dataclass, field
from typing import Callable, Awaitable

from app.agents.prompts import load_skill, list_skills


@dataclass
class Tool:
    """LLM function-calling 工具定义。"""

    name: str
    description: str
    parameters: dict  # OpenAI function-calling schema
    handler: Callable[[dict], Awaitable[str]] = field(default=None)

    def to_openai_schema(self) -> dict:
        """转换为 OpenAI function calling schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_schema(self) -> dict:
        """转换为 Anthropic tool use schema。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


# ---------------------------------------------------------------------------
# Skill Tool Factory
# ---------------------------------------------------------------------------


async def _load_skill_handler(args: dict) -> str:
    """load_skill 工具的处理函数。"""
    name = args.get("name", "")
    if not name:
        return "错误：name 参数必填"

    skill_names = list_skills()
    if name not in skill_names:
        available = ", ".join(sorted(skill_names)) or "（无）"
        return f"错误：技能 '{name}' 不存在。可用技能：{available}"

    content = load_skill(name)
    if not content:
        return f"错误：技能 '{name}' 内容为空"

    # 返回格式：技能名称 + 内容（让 LLM 直接使用）
    return f"【技能：{name}】\n\n{content}"


# ---------------------------------------------------------------------------
# 全局注册表
# ---------------------------------------------------------------------------

_SKILL_TOOL: Tool = Tool(
    name="load_skill",
    description=(
        "按需加载招聘领域技能文档。当 LLM 需要查询特定领域的操作手册、"
        "评估框架、题库或 SQL 模板时，调用此工具。\n"
        "可用技能：resume_parser（简历解析）、screening_framework（筛选框架）、"
        "interview_questions（面试题库）、sourcing_channels（渠道策略）、"
        "offer_negotiation（谈判策略）、onboarding_workflow（入职流程）、"
        "recruitment_analytics（招聘指标）"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "技能名称（不含 .md 后缀）",
                "enum": [
                    "resume_parser",
                    "screening_framework",
                    "interview_questions",
                    "sourcing_channels",
                    "offer_negotiation",
                    "onboarding_workflow",
                    "recruitment_analytics",
                ],
            }
        },
        "required": ["name"],
    },
    handler=_load_skill_handler,
)

# 全局工具列表（注册到 LLM）
_registered_tools: list[Tool] = [_SKILL_TOOL]

# 是否启用（env flag 控制）
_ENABLED = False


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def enable_skills():
    """启用 skills 工具（注册到 LLM tool schema）。"""
    global _ENABLED
    _ENABLED = True


def disable_skills():
    """禁用 skills 工具（从 LLM tool schema 移除）。"""
    global _ENABLED
    _ENABLED = False


def is_skills_enabled() -> bool:
    """返回当前 skills 工具启用状态。"""
    return _ENABLED


def get_available_tools() -> list[Tool]:
    """返回当前可用的 tool 列表（供 LLM 调用）。"""
    if not _ENABLED:
        return []
    return _registered_tools


def get_tools_schema(provider: str = "openai") -> list[dict]:
    """返回指定 provider 的 tool schema 列表。

    Args:
        provider: "openai" | "anthropic"

    Returns:
        tool schema 列表，可直接传给 LLM API。
    """
    if not _ENABLED:
        return []

    if provider == "anthropic":
        return [t.to_anthropic_schema() for t in _registered_tools]
    return [t.to_openai_schema() for t in _registered_tools]  # default: openai


async def call_tool(name: str, arguments: dict) -> str:
    """调用指定 tool 的 handler，返回结果字符串。

    Args:
        name: tool 名称
        arguments: LLM 传来的参数

    Returns:
        tool 执行结果（字符串）。

    Raises:
        ValueError: tool 不存在或未启用。
    """
    if not _ENABLED:
        raise ValueError("Skills 工具未启用")

    tool = next((t for t in _registered_tools if t.name == name), None)
    if not tool:
        raise ValueError(f"Tool '{name}' 不存在")

    if tool.handler is None:
        return f"Tool '{name}' 无 handler"

    return await tool.handler(arguments)


def get_skill_names() -> list[str]:
    """返回所有已注册的 skill 名称（供外部查询）。"""
    return list_skills()
