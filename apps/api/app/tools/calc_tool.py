"""Calculator tool — 安全数学表达式求值（v4 加 Pydantic InputModel）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.tools.metadata import Capability, register_tool


class CalculateInput(BaseModel):
    """calculate tool 输入。"""

    expression: str = Field(
        ...,
        pattern=r"^[0-9+\-*/().\s]+$",
        description="数学表达式（仅数字 + - * / ( ) 空格），如 1+2、3*4、(3+4)*2",
        examples=["1+2", "3*4", "(3+4)*2"],
    )


async def _handle_calculate(expression: str) -> str:
    allowed = set("0123456789+-*/(). ")
    if not all(c in allowed for c in expression):
        return f"错误: 表达式包含非法字符，仅支持 + - * / ( )"
    try:
        result = str(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307
        return result
    except Exception as e:
        return f"计算错误: {e}"


# 注册 metadata（含 Pydantic InputModel + capability）
register_tool(
    "calculate",
    retryable=True,
    max_retries=1,
    capability=Capability.READ,
    input_model=CalculateInput,
    description="执行基本数学运算（加、减、乘、除）。用于计算薪资、评分、统计等。",
    version="1.0.0",
    handler=_handle_calculate,
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行基本数学运算（加、减、乘、除）。用于计算薪资、评分、统计等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 1+2、3*4、10/2、(3+4)*2",
                    },
                },
                "required": ["expression"],
            },
        },
    },
]

handlers = {"calculate": _handle_calculate}
