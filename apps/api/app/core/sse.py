"""SSE (Server-Sent Events) 标准化推送工具。

标准格式:
    event: {event_type}
    data: {json_blob}

结束: 两个换行 \\n\\n
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def sse_event(event: str, data: Any, **extra: Any) -> str:
    """生成标准 SSE 消息块。

    SSE 协议中 data: 字段已经充当数据容器，因此 data 参数
    直接作为 JSON 序列化后的 data: 行内容，不额外包装。

    格式:
        event: {event_type}
        data: {json_blob}

    参数:
        event: 事件类型 (progress/error/timeout/complete/pending_updated 等)
        data:  事件数据 (会被 JSON 序列化)
        extra: 附加到 data 中的额外字段（当 data 为 dict 时合并）

    返回:
        完整的 SSE 消息字符串 (含末尾 \\n\\n)
    """
    if extra and isinstance(data, dict):
        payload = {**data, **extra}
    else:
        payload = data
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def sse_error(message: str) -> str:
    """生成标准 SSE 错误事件。"""
    return sse_event("error", {"message": message})


def sse_timeout() -> str:
    """生成标准 SSE 超时事件。"""
    return sse_event("timeout", {"message": "SSE connection timed out"})


def sse_headers() -> dict[str, str]:
    """返回 SSE 响应的标准 HTTP 头。"""
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Content-Type": "text/event-stream",
    }
