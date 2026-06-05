"""T6 埋点中心 — Prometheus 指标定义 + 事件准入白名单。

工业级 / 全局规划 / 稳定开发：
- 3 个 Counter（前端事件 / 接收 / API 请求）+ 1 个 Gauge（队列容量）
- 事件名白名单（防任意 string 污染 label）
- props 白名单（防 PII 泄漏）
- 异步安全（prom client Counter/Gauge 本身是 thread-safe，FastAPI 单进程多 async OK）
"""

from __future__ import annotations

import logging
import re
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

logger = logging.getLogger(__name__)

# ── Prometheus 指标 ──────────────────────────────────────────────
# Counter: 前端事件（按 event + card_type 切片）
frontend_event_total = Counter(
    "frontend_event_total",
    "Telemetry events from frontend",
    labelnames=("event", "card_type", "success"),
)

# Counter: telemetry 接收结果（accepted/rejected/filtered）
telemetry_received_total = Counter(
    "telemetry_received_total",
    "Telemetry batch received result",
    labelnames=("status",),  # accepted | rejected | filtered | error
)

# Counter: API 请求（中间件自动记）
api_request_total = Counter(
    "api_request_total",
    "API request count by method/path/status",
    labelnames=("method", "path", "status"),
)

# Gauge: 当前 telemetry 队列容量（前端上报使用，后端记录最后一次报告的队列大小）
telemetry_queue_size = Gauge(
    "telemetry_queue_size",
    "Last reported frontend telemetry queue size",
)


# ── 准入白名单 ─────────────────────────────────────────────────
# 事件名只允许已知产品事件，防任意 string 污染 label（label cardinality 爆炸是 prom 经典坑）
ALLOWED_EVENTS = frozenset(
    {
        "drawer_open",
        "drawer_close",
        "card_view",
        "card_export",
        "search_use",
        "hash_order_change",
        "drag_drop",
        "keyboard_nav",
        "approval_action",
        "notification_view",
        "error_boundary",
        "sse_parse_error",
    }
)

# props 白名单：除 event/ts 外的 metadata 只接受以下字段
# 黑名单规则自动应用于 value（不依赖 prop 名字）
ALLOWED_PROPS = frozenset(
    {
        "card_type",       # candidate_list / dashboard_stats / job_detail / ...
        "duration_ms",     # 持续时间
        "success",         # true / false
        "source",          # hash | button | keyboard
        "result_count",    # 搜索/过滤结果数
    }
)

# PII / 业务敏感 value 黑名单（regex 命中即过滤）
# 注意：保留 candidate_id / job_id 等业务 ID 在 events 之外的 analytics 中（funnel）
# 但不收集姓名 / 邮箱 / 电话 / 简历文本等 PII
_PII_VALUE_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"1[3-9]\d{9}"),               # 中国手机号
    re.compile(r"\+?\d[\d\s-]{7,}\d"),         # 国际电话
]
_PII_KEY_PATTERNS = [
    re.compile(r"(^|_)(name|email|phone|mobile|resume|address)(_|$)", re.IGNORECASE),
]


def _is_pii_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return any(p.search(value) for p in _PII_VALUE_PATTERNS)


def _is_pii_key(key: str) -> bool:
    return any(p.search(key) for p in _PII_KEY_PATTERNS)


def sanitize_props(props: dict[str, Any] | None) -> dict[str, Any]:
    """过滤 PII + 未知字段。返回新 dict，不修改入参。"""
    if not props:
        return {}
    out: dict[str, Any] = {}
    for k, v in props.items():
        if k not in ALLOWED_PROPS:
            continue
        if _is_pii_key(k) or _is_pii_value(v):
            continue
        out[k] = v
    return out


def record_event(event: str, props: dict[str, Any] | None) -> None:
    """记录单个前端事件（已被 router 验证通过）。"""
    sanitized = sanitize_props(props)
    card_type = sanitized.get("card_type", "none")
    success = str(sanitized.get("success", True)).lower()
    frontend_event_total.labels(event=event, card_type=str(card_type), success=success).inc()


def record_queue_size(size: int) -> None:
    """前端上报的当前队列容量。"""
    telemetry_queue_size.set(max(0, size))


def render_prometheus() -> tuple[bytes, str]:
    """返 (body, content_type) 给 /metrics 端点。"""
    return generate_latest(), CONTENT_TYPE_LATEST
