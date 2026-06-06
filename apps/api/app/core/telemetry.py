"""T6 埋点中心 + P5-7 监控告警 — Prometheus 指标 + 告警引擎 + 飞书 webhook。

指标分类:
- 业务埋点 (T6): frontend_event_total, telemetry_received_total, api_request_total, queue_size
- HTTP 健康 (P5-7): http_request_duration_seconds Histogram, http_requests_5xx_total Counter
- 数据库 (P5-7): db_pool_used Gauge, db_pool_size Gauge
- LLM (P5-7): llm_request_total Counter, llm_token_total Counter, llm_failure_total Counter
- 业务告警 (P5-7): llm_token_quota_remaining Gauge (per org)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)

# ── Prometheus 指标 ──────────────────────────────────────────────

# Counter: 前端事件
frontend_event_total = Counter(
    "frontend_event_total",
    "Telemetry events from frontend",
    labelnames=("event", "card_type", "success"),
)

# Counter: telemetry 接收
telemetry_received_total = Counter(
    "telemetry_received_total",
    "Telemetry batch received result",
    labelnames=("status",),
)

# Counter: API 请求
api_request_total = Counter(
    "api_request_total",
    "API request count by method/path/status",
    labelnames=("method", "path", "status"),
)

# Gauge: telemetry 队列容量
telemetry_queue_size = Gauge(
    "telemetry_queue_size",
    "Last reported frontend telemetry queue size",
)

# P5-7: HTTP 请求延迟直方图 (告警 p99 用)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "path"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

# P5-7: 5xx 错误计数 (告警用)
http_5xx_total = Counter(
    "http_5xx_total",
    "HTTP 5xx response count",
    labelnames=("method", "path"),
)

# P5-7: DB 连接池 (告警 DB>80% 用)
db_pool_used = Gauge(
    "db_pool_used",
    "Database connection pool in use",
)
db_pool_size = Gauge(
    "db_pool_size",
    "Database connection pool max size",
)

# P5-7: LLM 请求 / token / 失败
llm_request_total = Counter(
    "llm_request_total",
    "LLM API request count",
    labelnames=("model", "status"),
)
llm_token_total = Counter(
    "llm_token_total",
    "LLM token usage",
    labelnames=("model", "kind"),  # kind: prompt | completion
)
llm_failure_total = Counter(
    "llm_failure_total",
    "LLM API failure count",
    labelnames=("model", "error_type"),
)

# P5-7: 业务告警 (LLM token 配额剩余)
llm_token_quota_remaining = Gauge(
    "llm_token_quota_remaining",
    "LLM token quota remaining (current cycle)",
    labelnames=("org_id",),
)


# ── 准入白名单 ─────────────────────────────────────────────────
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

ALLOWED_PROPS = frozenset(
    {
        "card_type",
        "duration_ms",
        "success",
        "source",
        "result_count",
    }
)

_PII_VALUE_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"1[3-9]\d{9}"),
    re.compile(r"\+?\d[\d\s-]{7,}\d"),
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
    sanitized = sanitize_props(props)
    card_type = sanitized.get("card_type", "none")
    success = str(sanitized.get("success", True)).lower()
    frontend_event_total.labels(event=event, card_type=str(card_type), success=success).inc()


def record_queue_size(size: int) -> None:
    telemetry_queue_size.set(max(0, size))


def record_http_request(method: str, path: str, status: int, duration_seconds: float) -> None:
    """中间件调用: 记延迟 + 5xx 计数。"""
    path_label = _normalize_path(path)
    method_label = method.upper()
    http_request_duration_seconds.labels(method=method_label, path=path_label).observe(duration_seconds)
    api_request_total.labels(method=method_label, path=path_label, status=str(status)).inc()
    if 500 <= status < 600:
        http_5xx_total.labels(method=method_label, path=path_label).inc()


def record_llm_call(model: str, prompt_tokens: int, completion_tokens: int, success: bool, error_type: str = "") -> None:
    status_label = "success" if success else "failure"
    llm_request_total.labels(model=model, status=status_label).inc()
    if prompt_tokens:
        llm_token_total.labels(model=model, kind="prompt").inc(prompt_tokens)
    if completion_tokens:
        llm_token_total.labels(model=model, kind="completion").inc(completion_tokens)
    if not success and error_type:
        llm_failure_total.labels(model=model, error_type=error_type).inc()


def update_db_pool_metrics(used: int, size: int) -> None:
    db_pool_used.set(used)
    db_pool_size.set(size)


def update_llm_quota(org_id: str, remaining: int) -> None:
    llm_token_quota_remaining.labels(org_id=org_id).set(remaining)


def _normalize_path(path: str) -> str:
    """防 cardinality 爆炸: 把 /candidates/<uuid> 归一为 /candidates/:id"""
    if not path:
        return "unknown"
    parts = path.split("?")[0].split("/")
    normalized = []
    for part in parts:
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", part):
            normalized.append(":id")
        elif re.match(r"^\d+$", part):
            normalized.append(":n")
        else:
            normalized.append(part)
    return "/".join(normalized)[:128]


def render_prometheus() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


# ── P5-7 告警引擎 ──────────────────────────────────────────────

# 告警规则 (window_seconds 内 metric 满足 condition 触发)
# 4 条主规则 (Phase 4 plan 量化指标)
ALERT_RULES = [
    {
        "name": "http_5xx_rate_high",
        "description": "5xx 错误率 > 0.5% (1min 滑窗)",
        "metric": "http_5xx_total",
        "window_seconds": 60,
        "threshold": 0.005,
        "severity": "P1",
    },
    {
        "name": "http_p99_latency_high",
        "description": "HTTP p99 延迟 > 2s (1min 滑窗)",
        "metric": "http_request_duration_seconds",
        "window_seconds": 60,
        "threshold_p99_seconds": 2.0,
        "severity": "P1",
    },
    {
        "name": "db_pool_high",
        "description": "DB 连接池 > 80% (持续 1min)",
        "metric": "db_pool_used_ratio",
        "window_seconds": 60,
        "threshold": 0.80,
        "severity": "P1",
    },
    {
        "name": "llm_failure_rate_high",
        "description": "LLM 失败率 > 5% (5min 滑窗)",
        "metric": "llm_failure_rate",
        "window_seconds": 300,
        "threshold": 0.05,
        "severity": "P1",
    },
    {
        "name": "llm_token_quota_low",
        "description": "LLM token 配额 < 20% (提前 1 周预警)",
        "metric": "llm_token_quota_remaining_ratio",
        "window_seconds": 86400,
        "threshold": 0.20,
        "severity": "P2",
    },
]

# 5min 滑窗的 metric samples (内存, 单进程 OK)
class _SlidingWindow:
    def __init__(self, maxlen: int = 600):
        self.samples: deque = deque(maxlen=maxlen)

    def add(self, value: float, timestamp: float | None = None) -> None:
        self.samples.append((timestamp or time.time(), value))

    def rate_within(self, window_seconds: int, predicate) -> int:
        cutoff = time.time() - window_seconds
        return sum(1 for ts, v in self.samples if ts >= cutoff and predicate(v))

    def p99_within(self, window_seconds: int) -> Optional[float]:
        cutoff = time.time() - window_seconds
        values = [v for ts, v in self.samples if ts >= cutoff]
        if not values:
            return None
        values.sort()
        idx = int(len(values) * 0.99)
        return values[min(idx, len(values) - 1)]


_5xx_window = _SlidingWindow()
_latency_window = _SlidingWindow()
_llm_window = _SlidingWindow()
_db_pool_window = _SlidingWindow()


def record_metric_sample(metric: str, value: float) -> None:
    if metric == "http_5xx_total":
        _5xx_window.add(1.0 if value else 0.0)
    elif metric == "http_request_duration_seconds":
        _latency_window.add(value)
    elif metric == "llm_failure":
        _llm_window.add(1.0 if value else 0.0)
        _llm_window.add(0.0)
    elif metric == "llm_success":
        _llm_window.add(0.0)
    elif metric == "db_pool_ratio":
        _db_pool_window.add(value)


async def check_alerts() -> list[dict]:
    """每 30s 调用一次, 返回当前触发的告警列表。"""
    alerts: list[dict] = []
    for rule in ALERT_RULES:
        triggered = False
        actual_value: Optional[float] = None
        if rule["metric"] == "http_5xx_total":
            total = len(_5xx_window.samples)
            if total < 10:
                continue
            errors = _5xx_window.rate_within(rule["window_seconds"], lambda v: v > 0)
            actual_value = errors / max(total, 1)
            triggered = actual_value > rule["threshold"]
        elif rule["metric"] == "http_request_duration_seconds":
            actual_value = _latency_window.p99_within(rule["window_seconds"])
            triggered = actual_value is not None and actual_value > rule["threshold_p99_seconds"]
        elif rule["metric"] == "db_pool_used_ratio":
            cutoff = time.time() - rule["window_seconds"]
            values = [v for ts, v in _db_pool_window.samples if ts >= cutoff]
            if values:
                avg = sum(values) / len(values)
                actual_value = avg
                triggered = avg > rule["threshold"]
        elif rule["metric"] == "llm_failure_rate":
            cutoff = time.time() - rule["window_seconds"]
            total = sum(1 for ts, _ in _llm_window.samples if ts >= cutoff)
            if total < 5:
                continue
            failures = _llm_window.rate_within(rule["window_seconds"], lambda v: v > 0)
            actual_value = failures / max(total, 1)
            triggered = actual_value > rule["threshold"]

        if triggered:
            alerts.append({
                "name": rule["name"],
                "description": rule["description"],
                "severity": rule["severity"],
                "actual_value": actual_value,
                "threshold": rule["threshold"] or rule.get("threshold_p99_seconds"),
                "window_seconds": rule["window_seconds"],
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            })
    return alerts


async def send_feishu_alert(alert: dict) -> bool:
    """发飞书 webhook 通知。"""
    webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
    if not webhook:
        logger.warning("FEISHU_WEBHOOK_URL not set, alert suppressed: %s", alert["name"])
        return False
    emoji = "🔴" if alert["severity"] == "P1" else "🟡"
    content = (
        f"{emoji} [{alert['severity']}] {alert['name']}\n"
        f"{alert['description']}\n"
        f"实际: {alert['actual_value']:.4f if isinstance(alert['actual_value'], float) else alert['actual_value']}\n"
        f"阈值: {alert['threshold']}\n"
        f"窗口: {alert['window_seconds']}s\n"
        f"时间: {alert['triggered_at']}\n"
    )
    payload = {
        "msg_type": "text",
        "content": {"text": content},
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error("feishu webhook failed: %s", e)
        return False


async def run_alert_check_cycle() -> int:
    """每 30s 调一次: 检查告警 + 发飞书。返新触发数量。"""
    alerts = await check_alerts()
    sent = 0
    for alert in alerts:
        if await send_feishu_alert(alert):
            sent += 1
    return sent

