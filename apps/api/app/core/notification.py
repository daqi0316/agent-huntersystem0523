"""AI 通知领域模型与节流器（T3）

工业级 / 全局规划要点：
  - Pydantic schema 强类型，所有 emit 调用走类型校验
  - 节流器（throttle）防触发风暴：1 秒内同类通知 ≤ 1 条
  - fire-and-forget 设计：emit 失败不阻塞业务调用方
  - 持久化层分离：core/ 只放模型与工具，不依赖 FastAPI / Redis 直接调用
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Types ──

NotificationKind = Literal[
    "candidate_status_changed",
    "approval_requested",
    "approval_resolved",
    "system",
]


class Notification(BaseModel):
    """前端 NotificationsSection 展示的最小单元。

    强类型：避免事件 payload 任意 dict 传到 UI 出现运行时 undefined。
    """

    id: str
    user_id: str
    kind: NotificationKind
    title: str
    body: str
    action_url: str | None = None
    created_at: str
    read: bool = False


class StreamEntry(BaseModel):
    """Redis Stream 持久化记录。

    每条 stream entry 包含：
      - id: Redis Stream 自动生成的 msg_id（如 "1234567890-0"），用于 Last-Event-ID 重放
      - envelope: SSE 事件字符串（event + data 拼接），与 Redis pub/sub 格式兼容
    """

    id: str
    envelope: str


# ── Throttle ──


class _Throttle:
    """同 user × 同 kind 节流器：1 秒内同类通知 ≤ 1 条。

    实现：内存 dict + 滑动窗口（last emit ts per key）。
    进程内可见；多实例各自独立节流（acceptable — 用户视角不会爆发）。

    为什么不用 Redis：节流是"软约束"，允许极少数超出，避免引入额外故障点。
    """

    def __init__(self, window_seconds: float = 1.0) -> None:
        self.window = window_seconds
        self._last_emit: dict[tuple[str, str], float] = {}

    def allow(self, user_id: str, kind: str) -> bool:
        key = (user_id, kind)
        now = time.monotonic()
        last = self._last_emit.get(key, 0.0)
        if now - last < self.window:
            return False
        self._last_emit[key] = now
        return True

    def reset(self) -> None:
        self._last_emit.clear()


_throttle = _Throttle(window_seconds=1.0)


def reset_throttle() -> None:
    """测试 helper：重置节流状态。"""
    _throttle.reset()


def should_emit(user_id: str, kind: str) -> bool:
    """判断是否允许 emit（节流 gate）。"""
    return _throttle.allow(user_id, kind)


# ── Fire-and-forget emit 包装 ──


async def safe_emit(coro_factory: Any, *args: Any, **kwargs: Any) -> None:
    """把 emit 调用包成 fire-and-forget，失败只 log 不抛。

    用法：
        asyncio.create_task(safe_emit(emit_to_user, user_id, event, data))

    比 `asyncio.create_task(emit_to_user(...))` 多了：捕获 Exception + log，不让
    background task 失败导致 "Task exception was never retrieved" warning。
    """

    try:
        coro = coro_factory(*args, **kwargs)
        await coro
    except Exception as e:  # pragma: no cover - 永远兜底
        logger.warning("notification: emit failed (%s) args=%s kwargs=%s", e, args, kwargs)
