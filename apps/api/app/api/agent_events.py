"""Agent Event Stream — 跨设备实时同步 Phase 4.1

事件类型：
  - ping                心跳（每 15s，防止代理超时）
  - data_card.created   新数据卡片（由其它设备创建，本设备接收后写入本地 store）
  - context.updated     上下文变化（候选人/职位/话题）
  - approval.requested  新审批请求

设计：
  - 内存 pub/sub（per-user queue），或 Redis pub/sub（REDIS_URL 启用时）
  - 自动降级：Redis 不可用时退回内存
  - 与 /agent/chat 解耦：/agent/chat 完成后 emit → 推送到所有连接
  - 接收端 unsubscribe 自动清理
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user_id
from app.core.sse import sse_event, sse_headers

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 15  # seconds

# ── In-memory pub/sub fallback ──
# _queues[user_id] = list[asyncio.Queue]
_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

# ── Redis pub/sub (optional) ──
_REDIS_URL: str | None = os.getenv("REDIS_URL")
_REDIS_CHANNEL_PREFIX = "agent_events:user:"

_redis_client: Any | None = None
_redis_checked = False


async def _try_get_redis() -> Any | None:
    """尝试连接 Redis，失败返回 None（仅检查一次）。"""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    if not _REDIS_URL:
        logger.info("agent_events: REDIS_URL not set, using in-memory pub/sub")
        return None
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(_REDIS_URL, decode_responses=True)
        await client.ping()
        _redis_client = client
        logger.info("agent_events: connected to Redis at %s", _REDIS_URL)
        return client
    except Exception as e:
        logger.warning("agent_events: Redis connection failed (%s), using in-memory", e)
        return None


def _redis_channel(user_id: str) -> str:
    return f"{_REDIS_CHANNEL_PREFIX}{user_id}"


async def emit_to_user(user_id: str, event: str, data: dict[str, Any]) -> None:
    """Emit an event to all SSE connections of a user.

    双通道：
      1. 内存 queue（同进程内的所有连接立即收到）
      2. Redis pub/sub（跨进程 / 跨实例的连接也收到，启用时）
    """
    payload = sse_event(event, data)

    for q in _queues.get(user_id, []):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("agent_events: queue full for user %s", user_id)

    redis_client = await _try_get_redis()
    if redis_client is not None:
        try:
            envelope = json.dumps({"event": event, "data": data})
            await redis_client.publish(_redis_channel(user_id), envelope)
        except Exception as e:
            logger.warning("agent_events: Redis publish failed (%s)", e)


async def emit_data_card(user_id: str, card: dict[str, Any]) -> None:
    """Emit data_card.created event."""
    await emit_to_user(user_id, "data_card.created", card)


async def emit_context_update(user_id: str, context: dict[str, Any]) -> None:
    """Emit context.updated event."""
    await emit_to_user(user_id, "context.updated", context)


async def emit_approval_requested(user_id: str, approval: dict[str, Any]) -> None:
    """Emit approval.requested event."""
    await emit_to_user(user_id, "approval.requested", approval)


async def emit_approval_resolved(user_id: str, resolution: dict[str, Any]) -> None:
    """Emit approval.resolved event."""
    await emit_to_user(user_id, "approval.resolved", resolution)


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
    """SSE event generator for a single user connection.

    数据来源：
      - 本连接专属的 asyncio.Queue（in-memory 通道）
      - 若 Redis 启用，额外订阅 Redis pub/sub channel（跨进程通道）
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues[user_id].append(queue)
    logger.info(
        "agent_events: user=%s connected, total=%d", user_id, len(_queues[user_id])
    )

    redis_sub = None
    redis_client = await _try_get_redis()
    if redis_client is not None:
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(_redis_channel(user_id))
            redis_sub = pubsub
            logger.info("agent_events: user=%s subscribed to Redis channel", user_id)
        except Exception as e:
            logger.warning("agent_events: Redis subscribe failed (%s)", e)

    try:
        yield sse_event("connected", {"user_id": user_id})

        while True:
            try:
                payload = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT_INTERVAL
                )
                yield payload
            except asyncio.TimeoutError:
                if redis_sub is not None:
                    try:
                        msg = await redis_sub.get_message(
                            ignore_subscribe_messages=True, timeout=0.1
                        )
                        if msg and msg.get("type") == "message":
                            envelope = json.loads(msg["data"])
                            yield sse_event(envelope["event"], envelope["data"])
                            continue
                    except Exception as e:
                        logger.debug("agent_events: redis poll: %s", e)
                yield sse_event("ping", {"ts": asyncio.get_event_loop().time()})
    except asyncio.CancelledError:
        logger.info("agent_events: user=%s disconnected", user_id)
        raise
    finally:
        if redis_sub is not None:
            try:
                await redis_sub.unsubscribe()
                await redis_sub.close()
            except Exception:
                pass
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

    跨进程：
      - REDIS_URL 环境变量启用时，所有事件经 Redis pub/sub 广播
      - 多实例部署时，连接在不同实例上的用户也能收到事件
    """
    return StreamingResponse(
        _generator(user_id),
        media_type="text/event-stream",
        headers=sse_headers(),
    )
