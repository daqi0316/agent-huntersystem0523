"""Greet tool — 个性化问候语生成（v4 加 Pydantic InputModel）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.tools.metadata import Capability, register_tool


class GreetInput(BaseModel):
    """greet tool 输入。"""

    name: str = Field(..., min_length=1, max_length=100, description="用户姓名")
    language: Literal["zh", "en", "ja"] = Field(
        default="zh", description="问候语语言（默认中文）"
    )


async def _handle_greet(name: str, language: str = "zh") -> str:
    greetings = {
        "zh": f"你好，{name}！欢迎使用 AI 招聘系统。",
        "en": f"Hello, {name}! Welcome to the AI Recruitment System.",
        "ja": f"こんにちは、{name}！AI採用システムへようこそ。",
    }
    return greetings.get(language, greetings["zh"])


register_tool(
    "greet",
    retryable=True,
    max_retries=1,
    capability=Capability.READ,
    input_model=GreetInput,
    description="生成个性化问候语，支持中、英、日三种语言。",
    version="1.0.0",
    handler=_handle_greet,
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "greet",
            "description": "生成个性化问候语，支持中、英、日三种语言。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "用户姓名",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["zh", "en", "ja"],
                        "description": "问候语语言（默认中文）",
                        "default": "zh",
                    },
                },
                "required": ["name"],
            },
        },
    },
]

handlers = {"greet": _handle_greet}
