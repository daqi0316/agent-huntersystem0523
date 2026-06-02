"""Calculator tool — 安全数学表达式求值。"""

from __future__ import annotations


async def _handle_calculate(expression: str) -> str:
    allowed = set("0123456789+-*/(). ")
    if not all(c in allowed for c in expression):
        return f"错误: 表达式包含非法字符，仅支持 + - * / ( )"
    try:
        result = str(eval(expression, {"__builtins__": {}}, {}))
        return result
    except Exception as e:
        return f"计算错误: {e}"


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
