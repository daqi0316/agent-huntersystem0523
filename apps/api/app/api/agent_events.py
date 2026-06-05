"""Agent Event Stream — 跨设备实时同步 (Phase 4.1) + 离线重放 (T3)

事件类型：
  - ping                心跳（每 15s，防止代理超时）
  - data_card.created   新数据卡片（由其它设备创建，本设备接收后写入本地 store）
  - context.updated     上下文变化（候选人/职位/话题）
  - approval.requested  新审批请求
  - approval.resolved   审批通过/拒绝
  - chat_response       跨设备 chat 同步
  - notification.fired  AI 业务通知（候选人状态变更等）— T3 新增

三层架构（T3 工业级）:
  1. 内存 pub/sub — 同进程内所有 SSE 连接立即收到
  2. Redis pub/sub — 跨进程 / 跨实例实时推送
  3. Redis Streams 持久化 + Last-Event-ID 重放 — 离线追赶（断线期间的 events）

降级顺序: Streams → pub/sub → 内存；任一层失败自动降级下一层。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_user_id_sse
from app.core.notification import should_emit
from app.core.sse import sse_event, sse_headers

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 15  # seconds
STREAM_MAXLEN = 1000  # Redis Stream 容量上限（plan §3 验收）
REPLAY_BATCH_LIMIT = 50  # 单次重连最多 replay 50 条（plan §3 验收）

# ── In-memory pub/sub fallback ──
# _queues[user_id] = list[asyncio.Queue]
_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

# ── Redis pub/sub (optional) ──
_REDIS_URL: str | None = os.getenv("REDIS_URL")
_REDIS_CHANNEL_PREFIX = "agent_events:user:"
_REDIS_STREAM_PREFIX = "agent_events:stream:"

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


def _redis_stream_key(user_id: str) -> str:
    return f"{_REDIS_STREAM_PREFIX}{user_id}"


async def _persist_to_stream(user_id: str, event: str, data: dict[str, Any]) -> str | None:
    """Redis Streams 持久化（XADD MAXLEN ~ 1000）。

    返回 Redis Stream 生成的 msg_id（如 "1234567890-0"），用于 Last-Event-ID 重放。
    失败返回 None（不阻塞主流程，pub/sub 仍工作）。
    """
    client = await _try_get_redis()
    if client is None:
        return None
    try:
        envelope = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        msg_id = await client.xadd(
            _redis_stream_key(user_id),
            {"envelope": envelope},
            maxlen=STREAM_MAXLEN,
            approximate=True,  # MAXLEN ~ 1000 近似裁剪，性能更好
        )
        return msg_id
    except Exception as e:
        logger.warning("agent_events: XADD failed (%s)", e)
        return None


async def _replay_since(user_id: str, last_event_id: str) -> list[tuple[str, str]]:
    """Redis Streams 重放（XRANGE (last_event_id, +  COUNT 50）。

    返回 [(msg_id, envelope), ...] 按时间升序。
    Redis XRANGE 区间：'(id' 表示不包含该 id。
    """
    client = await _try_get_redis()
    if client is None:
        return []
    try:
        rows = await client.xrange(
            _redis_stream_key(user_id),
            min=f"({last_event_id}",  # 排除客户端已收到的
            max="+",
            count=REPLAY_BATCH_LIMIT,
        )
        return [(mid, fields.get("envelope", "")) for mid, fields in rows]
    except Exception as e:
        logger.warning("agent_events: XRANGE failed (%s)", e)
        return []


async def emit_to_user(
    user_id: str,
    event: str,
    data: dict[str, Any],
    *,
    persist: bool = True,
) -> str | None:
    """Emit an event to all SSE connections of a user.

    三层通道（按顺序）：
      1. 内存 queue（同进程内所有连接立即收到）
      2. Redis pub/sub（跨进程 / 跨实例实时推送）
      3. Redis Streams 持久化（断线重连时 Last-Event-ID 重放）

    Args:
        persist: True = 写 Stream（默认）；False = 仅实时推送（如 ping 不持久化）

    Returns:
        Redis Stream msg_id（持久化成功时）；None 表示 Redis 不可用或 persist=False
    """
    payload = sse_event(event, data)

    for q in _queues.get(user_id, []):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("agent_events: queue full for user %s", user_id)

    redis_client = await _try_get_redis()
    msg_id: str | None = None

    if redis_client is not None:
        # 实时推送（pub/sub）
        try:
            envelope = json.dumps({"event": event, "data": data}, ensure_ascii=False)
            await redis_client.publish(_redis_channel(user_id), envelope)
        except Exception as e:
            logger.warning("agent_events: Redis publish failed (%s)", e)

        # 持久化（Streams）— 异步 fire-and-forget 不阻塞调用方
        if persist:
            try:
                msg_id = await redis_client.xadd(
                    _redis_stream_key(user_id),
                    {"envelope": json.dumps({"event": event, "data": data}, ensure_ascii=False)},
                    maxlen=STREAM_MAXLEN,
                    approximate=True,
                )
            except Exception as e:
                logger.warning("agent_events: XADD failed (%s)", e)

    return msg_id


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


async def emit_ai_notification(
    user_id: str,
    kind: str,
    title: str,
    body: str,
    action_url: str | None = None,
) -> str | None:
    """业务通知（T3 新增）：emit notification.fired 事件 + 节流。

    触发场景示例:
        await emit_ai_notification(
            user_id, kind="candidate_status_changed",
            title="候选人状态变更",
            body=f"{candidate.name} → {new_status}",
            action_url=f"/candidates/{candidate.id}",
        )

    节流: 同 user × 同 kind 1 秒内仅 1 条（防止批量更新风暴）。
    Returns: stream msg_id（持久化成功时）；None = 节流跳过 或 Redis 不可用
    """
    from datetime import UTC, datetime

    if not should_emit(user_id, kind):
        logger.debug("emit_ai_notification: throttled user=%s kind=%s", user_id, kind)
        return None

    notification = {
        "id": f"notif_{user_id}_{int(asyncio.get_event_loop().time() * 1000)}",
        "user_id": user_id,
        "kind": kind,
        "title": title,
        "body": body,
        "action_url": action_url,
        "created_at": datetime.now(UTC).isoformat(),
    }

    return await emit_to_user(user_id, "notification.fired", notification)


async def _generator(user_id: str, last_event_id: str | None = None):
    """SSE event generator for a single user connection.

    T3 改造：
      - 新增 last_event_id 参数：连接时若提供，先 XRANGE 重放离线期间 events
      - 重放完毕后再进入正常 pub/sub 监听循环
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues[user_id].append(queue)
    logger.info(
        "agent_events: user=%s connected (last_event_id=%s), total=%d",
        user_id,
        last_event_id,
        len(_queues[user_id]),
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
        # connected 事件携带 user_id（前端 onopen 标记）
        yield sse_event("connected", {"user_id": user_id})

        # T3: 离线重放（Last-Event-ID）
        if last_event_id:
            replayed = await _replay_since(user_id, last_event_id)
            for msg_id, envelope_str in replayed:
                try:
                    envelope = json.loads(envelope_str)
                    # 标记 id: 前端 EventSource 会把这条当 lastEventId
                    payload = sse_event(envelope["event"], envelope["data"], id=msg_id)
                    yield payload
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("agent_events: skip malformed envelope (%s)", e)
                    continue
            logger.info(
                "agent_events: user=%s replayed %d events since %s",
                user_id,
                len(replayed),
                last_event_id,
            )

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
                # ping 不持久化（节省 Stream 空间）
                yield sse_event(
                    "ping", {"ts": asyncio.get_event_loop().time()}
                )
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
    user_id: str = Depends(get_user_id_sse),
    last_event_id: str | None = Query(
        None,
        description="T3 断线重连：Redis Stream msg_id，重放该 id 之后的所有 events",
        pattern=r"^\d+-\d+$",
    ),
):
    """SSE 端点：订阅 agent 实时事件（含 T3 离线重放）。

    鉴权：SSE 专用 dep（header Bearer 或 ?token= query，EventSource 用后者）
    """
    return StreamingResponse(
        _generator(user_id, last_event_id=last_event_id),
        media_type="text/event-stream",
        headers=sse_headers(),
    )

