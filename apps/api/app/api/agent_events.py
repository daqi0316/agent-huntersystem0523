"""Agent Event Stream — 跨设备实时同步 Phase 4.1

事件类型：
  - ping                心跳（每 15s，防止代理超时）
  - data_card.created   新数据卡片（由其它设备创建，本设备接收后写入本地 store）
  - context.updated     上下文变化（候选人/职位/话题）
  - approval.requested  新审批请求

设计：
  - 内存 pub/sub（per-user queue），未来可换 Redis
  - 与 /agent/chat 解耦：/agent/chat 完成后 emit → 推送到所有连接
  - 接收端 unsubscribe 自动清理
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user_id
from app.core.sse import sse_event, sse_headers

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 15  # seconds

# ── In-memory pub/sub ──
# _queues[user_id] = list[asyncio.Queue]
_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def emit_to_user(user_id: str, event: str, data: dict[str, Any]) -> None:
    """Emit an event to all SSE connections of a user."""
    payload = sse_event(event, data)
    for q in _queues.get(user_id, []):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("agent_events: queue full for user %s", user_id)


async def emit_data_card(user_id: str, card: dict[str, Any]) -> None:
    """Emit data_card.created event."""
    await emit_to_user(user_id, "data_card.created", card)


async def emit_context_update(user_id: str, context: dict[str, Any]) -> None:
    """Emit context.updated event."""
    await emit_to_user(user_id, "context.updated", context)


async def emit_approval_requested(user_id: str, approval: dict[str, Any]) -> None:
    """Emit approval.requested event."""
    await emit_to_user(user_id, "approval.requested", approval)


async def emit_chat_response(
    user_id: str,
    reply: str,
    tool_calls: list[dict[str, Any]],
    model: str = "",
) -> None:
    """Emit chat_response event after /agent/chat completes.

    其它设备的 EventSource 收到后，前端用 parseDataCardsFromMessage 解析
    产生 DataCard，跨设备数据卡片同步闭环。
    """
    await emit_to_user(
        user_id,
        "chat_response",
        {
            "reply": reply,
            "tool_calls": tool_calls,
            "model": model,
        },
    )


async def _generator(user_id: str):
    """SSE event generator for a single user connection."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues[user_id].append(queue)
    logger.info(
        "agent_events: user=%s connected, total=%d", user_id, len(_queues[user_id])
    )
    try:
        # 立即发一个 connected 事件
        yield sse_event("connected", {"user_id": user_id})

        while True:
            try:
                payload = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT_INTERVAL
                )
                yield payload
            except asyncio.TimeoutError:
                # 心跳保活
                yield sse_event("ping", {"ts": asyncio.get_event_loop().time()})
    except asyncio.CancelledError:
        logger.info("agent_events: user=%s disconnected", user_id)
        raise
    finally:
        try:
            _queues[user_id].remove(queue)
        except ValueError:
            pass
        if not _queues[user_id]:
            del _queues[user_id]


@router.get("/events")
async def agent_events(
    user_id: str = Depends(get_current_user_id),
):
    """SSE 端点：订阅 agent 实时事件。

    事件流：
      - connected        连接建立
      - ping             每 15s 心跳
      - data_card.created  新数据卡片（来自其它设备）
      - context.updated    上下文变化
      - approval.requested 审批请求
    """
    return StreamingResponse(
        _generator(user_id),
        media_type="text/event-stream",
        headers=sse_headers(),
    )
