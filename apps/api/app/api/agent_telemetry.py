"""T6 前端埋点接收端点 — POST /api/v1/agent/telemetry。

工业级 / 全局规划 / 稳定开发：
- 事件名白名单 + props 白名单 + PII 过滤（在 telemetry.sanitize_props）
- 接受批量（每批 ≤100 条），避免高频小包
- 不强制鉴权（埋点是匿名的产品行为，但限流 — 通过全局中间件）
- 上报失败不影响前端：单条失败仅 +1 rejected，不抛异常
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.telemetry import (
    ALLOWED_EVENTS,
    record_event,
    record_queue_size,
    sanitize_props,
    telemetry_received_total,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class TelemetryEvent(BaseModel):
    event: str = Field(..., max_length=64)
    props: dict[str, Any] | None = None
    ts: float | None = None  # 客户端时间戳（可选，调试用）


class TelemetryBatch(BaseModel):
    events: list[TelemetryEvent] = Field(..., max_length=100)


@router.post("/telemetry")
async def ingest_telemetry(batch: TelemetryBatch, request: Request) -> dict[str, Any]:
    """接收一批前端事件。

    Returns:
        {accepted: N, rejected: M, queue_size: int} — 实际入库条数与队列大小
    """
    accepted = 0
    rejected = 0
    filtered = 0

    for evt in batch.events:
        if evt.event not in ALLOWED_EVENTS:
            rejected += 1
            continue

        sanitized = sanitize_props(evt.props)
        if not sanitized and evt.props:
            # 用户传了 props 但全被过滤
            filtered += 1

        try:
            record_event(evt.event, sanitized)
            accepted += 1
        except Exception as e:
            logger.warning("telemetry record failed: %s", e)
            rejected += 1

    if accepted > 0:
        telemetry_received_total.labels(status="accepted").inc(accepted)
    if rejected > 0:
        telemetry_received_total.labels(status="rejected").inc(rejected)
    if filtered > 0:
        telemetry_received_total.labels(status="filtered").inc(filtered)

    # 记录前端上报的当前队列容量（取 batch.size 作为最近一次的快照）
    record_queue_size(len(batch.events))

    return {
        "accepted": accepted,
        "rejected": rejected,
        "filtered": filtered,
    }
