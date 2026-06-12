"""
事件总线 — 引擎事件的发布/订阅（★ 工程化扩展）
支持钉钉/企业微信告警
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Any
import structlog

logger = structlog.get_logger()


class EngineEvent(str, Enum):
    """引擎事件类型"""
    ENGINE_STARTED = "engine.started"
    ENGINE_STOPPED = "engine.stopped"
    ENGINE_DEGRADED = "engine.degraded"
    ENGINE_RECOVERED = "engine.recovered"
    FETCH_SUCCESS = "fetch.success"
    FETCH_FAILED = "fetch.failed"
    FALLBACK_TRIGGERED = "fallback.triggered"
    PAGE_BLOCKED = "page.blocked"
    CAPTCHA_DETECTED = "captcha.detected"


class EventBus:
    """事件总线 — 引擎事件的发布/订阅"""

    _handlers: dict[EngineEvent, list[Callable]] = {}

    @classmethod
    def subscribe(cls, event: EngineEvent, handler: Callable):
        """订阅事件"""
        cls._handlers.setdefault(event, []).append(handler)
        logger.debug("事件订阅", event=event.value, handler=handler.__name__)

    @classmethod
    async def publish(cls, event: EngineEvent, **data):
        """发布事件"""
        for handler in cls._handlers.get(event, []):
            try:
                await handler(event, **data)
            except Exception as e:
                logger.error("事件处理器失败", event=event.value, error=str(e))

    @classmethod
    def unsubscribe(cls, event: EngineEvent, handler: Callable):
        """取消订阅"""
        handlers = cls._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    @classmethod
    def clear(cls):
        """清除所有订阅（主要用于测试）"""
        cls._handlers.clear()


# ── 内置告警 handler ──

async def dingtalk_alert(event: EngineEvent, **data):
    """钉钉告警 — 通过 Webhook 发送"""
    import httpx

    webhook = data.get("webhook_url")
    if not webhook:
        return

    message = {
        "msgtype": "text",
        "text": {
            "content": f"[引擎告警] 事件: {event.value}\n"
                       f"详情: {data.get('message', '')}",
        },
    }

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(webhook, json=message)


async def wecom_alert(event: EngineEvent, **data):
    """企业微信告警"""
    import httpx

    webhook = data.get("webhook_url")
    if not webhook:
        return

    message = {
        "msgtype": "text",
        "text": {
            "content": f"[引擎告警] 事件: {event.value}\n"
                       f"详情: {data.get('message', '')}",
        },
    }

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(webhook, json=message)


__all__ = [
    "EngineEvent",
    "EventBus",
    "dingtalk_alert",
    "wecom_alert",
]
