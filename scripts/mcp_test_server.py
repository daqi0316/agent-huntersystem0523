"""MCP 测试服务器 — 用于验证 AI Recruitment 系统的 MCP 扩展功能。

启动:
  uvicorn scripts.mcp_test_server:app --host 0.0.0.0 --port 8002 --reload

然后在前端 MCP 页面添加:
  URL: http://localhost:8002/mcp
  协议: streamable-http
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="MCP Test Server", version="1.0.0")

# ── 工具定义 ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "calculate",
        "description": "执行基本数学运算（加、减、乘、除）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 1+2、3*4、10/2",
                },
            },
            "required": ["expression"],
        },
    },
    {
        "name": "greet",
        "description": "生成个性化问候语",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "用户姓名"},
                "language": {
                    "type": "string",
                    "enum": ["zh", "en", "ja"],
                    "description": "问候语语言",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_current_time",
        "description": "获取当前服务器的日期和时间",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "时区（可选，默认 Asia/Shanghai）",
                },
            },
        },
    },
    {
        "name": "search_documents",
        "description": "模拟文档搜索 — 返回预置的招聘相关文档结果",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回结果数量（默认 3）"},
            },
            "required": ["query"],
        },
    },
]

# ── 工具实现 ─────────────────────────────────────────────


async def handle_calculate(args: dict[str, Any]) -> list[dict]:
    expression = args.get("expression", "")
    try:
        # 安全求值 — 只允许基本算术
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expression):
            result = "错误: 表达式包含非法字符"
        else:
            result = str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        result = f"计算错误: {e}"
    return [{"type": "text", "text": result}]


async def handle_greet(args: dict[str, Any]) -> list[dict]:
    name = args.get("name", "")
    lang = args.get("language", "zh")
    greetings = {
        "zh": f"你好，{name}！欢迎使用 AI 招聘系统。",
        "en": f"Hello, {name}! Welcome to the AI Recruitment System.",
        "ja": f"こんにちは、{name}！AI採用システムへようこそ。",
    }
    text = greetings.get(lang, greetings["zh"])
    return [{"type": "text", "text": text}]


async def handle_get_current_time(args: dict[str, Any]) -> list[dict]:
    from datetime import datetime, timezone, timedelta

    tz_name = args.get("timezone", "Asia/Shanghai")
    tz_map = {
        "Asia/Shanghai": 8,
        "Asia/Tokyo": 9,
        "America/New_York": -5,
        "America/Los_Angeles": -8,
        "Europe/London": 0,
        "UTC": 0,
    }
    offset = tz_map.get(tz_name, 8)
    now = datetime.now(timezone.utc) + timedelta(hours=offset)
    return [{
        "type": "text",
        "text": f"当前时间 ({tz_name}): {now.strftime('%Y-%m-%d %H:%M:%S')}",
    }]


async def handle_search_documents(args: dict[str, Any]) -> list[dict]:
    query = args.get("query", "")
    limit = min(args.get("limit", 3), 10)

    docs = [
        {"title": "招聘流程最佳实践", "category": "流程", "content": "标准招聘流程包括：需求确认→发布职位→简历筛选→面试→Offer→入职。每个环节需要明确责任人和时间节点。"},
        {"title": "面试评估标准指南", "category": "评估", "content": "建议从技术能力、沟通能力、文化契合度、成长潜力四个维度评估候选人，每项 1-5 分。"},
        {"title": "候选人体验优化手册", "category": "体验", "content": "从投递到入职，保持 48 小时内响应，提供明确 feedback，减少候选人等待时间。"},
        {"title": "AI 初筛配置说明", "category": "技术", "content": "AI 初筛支持自定义筛选维度、权重、阈值。建议初始设置：技能匹配 40%，经验 30%，教育 20%，其他 10%。"},
        {"title": "JD 编写方法论", "category": "内容", "content": "好的 JD 应包含：职位概述、职责描述、任职要求、加分项、团队介绍。避免使用歧视性语言。"},
    ]

    matched = [d for d in docs if query.lower() in d["title"].lower() or query.lower() in d["category"].lower()]
    if not matched:
        matched = docs[:limit]

    text = "\n---\n".join(
        f"【{d['title']}】({d['category']})\n{d['content']}" for d in matched[:limit]
    )
    return [{"type": "text", "text": text or "未找到匹配结果"}]


HANDLERS = {
    "calculate": handle_calculate,
    "greet": handle_greet,
    "get_current_time": handle_get_current_time,
    "search_documents": handle_search_documents,
}

# ── MCP Endpoint ─────────────────────────────────────────


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    body = await request.json()
    method = body.get("method", "")
    msg_id = body.get("id", None)

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "mcp-test-server",
                    "version": "1.0.0",
                },
            },
        }

    if method == "notifications/initialized":
        return JSONResponse(content={}, status_code=202)

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = HANDLERS.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"未知工具: {tool_name}"},
            }

        try:
            content = await handler(arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": content},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32000, "message": str(e)},
            }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"未知方法: {method}"},
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mcp-test-server"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
