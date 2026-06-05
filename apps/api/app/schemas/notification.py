"""通知 Schemas — Pydantic 模型 (T3)

设计上：
  - API 层（agent_events.py）用这些 schema 校验 emit / replay payload
  - 前端通过 SSE 收到 JSON 字符串后用 zod 解析；这里只定义后端契约
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NotificationKind = Literal[
    "candidate_status_changed",
    "approval_requested",
    "approval_resolved",
    "system",
]


class NotificationPayload(BaseModel):
    """emit_ai_notification 接收的参数（service 层用）"""

    user_id: str
    kind: NotificationKind
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=500)
    action_url: str | None = None


class LastEventIdQuery(BaseModel):
    """SSE 客户端断线重连时携带的 query param"""

    last_event_id: str | None = Field(
        None,
        description="Redis Stream msg_id；XRANGE 起点（不含）",
        pattern=r"^\d+-\d+$",
    )
