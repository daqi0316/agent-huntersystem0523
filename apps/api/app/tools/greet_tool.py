"""Greet tool — 个性化问候语生成。"""

from __future__ import annotations


async def _handle_greet(name: str, language: str = "zh") -> str:
    greetings = {
        "zh": f"你好，{name}！欢迎使用 AI 招聘系统。",
        "en": f"Hello, {name}! Welcome to the AI Recruitment System.",
        "ja": f"こんにちは、{name}！AI採用システムへようこそ。",
    }
    return greetings.get(language, greetings["zh"])


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
