"""MCP 域告警 + 监控 hook（v4 PR-4d：Sentry 集成 + 阈值告警）。

设计：
  - Sentry 集成：现有 sentry-sdk[fastapi]（已有），不重复装
  - 告警项：
    1. MCP server restart 次数超阈值（默认 5/小时）
    2. tool call 异常率 > 5%
    3. 关键工具（destructive capability）调用失败
  - 触发方式：调用告警函数（不阻塞主流程）

为什么不用 OpenTelemetry alerting？
  - OTel 复杂，PR-5+ 引入
  - 当前 prometheus_client 全局 registry 已暴露 mcp_* 指标
  - 简单 Sentry capture_message 就够工程化起步
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


# ── 配置（环境变量可调）────────────────────────────────────────
ALERT_RESTART_THRESHOLD = int(os.getenv("MCP_ALERT_RESTART_THRESHOLD", "5"))
ALERT_ERROR_RATE_THRESHOLD = float(os.getenv("MCP_ALERT_ERROR_RATE_THRESHOLD", "0.05"))
ALERT_WINDOW_SECONDS = int(os.getenv("MCP_ALERT_WINDOW_SECONDS", "3600"))  # 1h


# ── Restart 监控 ─────────────────────────────────────────────
class RestartTracker:
    """跟踪 server restart 次数，超阈值告警。"""

    def __init__(self) -> None:
        self._restarts: dict[str, list[float]] = {}  # server_id → [timestamp, ...]

    def record_restart(self, server_id: str) -> None:
        now = time.time()
        self._restarts.setdefault(server_id, []).append(now)
        # 清理窗口外的
        cutoff = now - ALERT_WINDOW_SECONDS
        self._restarts[server_id] = [t for t in self._restarts[server_id] if t > cutoff]
        # 阈值告警
        if len(self._restarts[server_id]) >= ALERT_RESTART_THRESHOLD:
            alert_restart_threshold(server_id, len(self._restarts[server_id]))

    def count_in_window(self, server_id: str) -> int:
        return len(self._restarts.get(server_id, []))

    def reset(self, server_id: str) -> None:
        self._restarts.pop(server_id, None)


# ── 错误率监控 ──────────────────────────────────────────────
class ErrorRateTracker:
    """跟踪 call_tool 成功/失败，超阈值告警。"""

    def __init__(self) -> None:
        self._calls: dict[str, list[tuple[float, bool]]] = {}  # tool → [(ts, success)]

    def record_call(self, tool: str, success: bool) -> None:
        now = time.time()
        self._calls.setdefault(tool, []).append((now, success))
        cutoff = now - ALERT_WINDOW_SECONDS
        self._calls[tool] = [(t, s) for t, s in self._calls[tool] if t > cutoff]
        # 检查错误率
        recent = self._calls[tool]
        if len(recent) >= 10:  # 至少 10 次调用才计算
            errors = sum(1 for _, s in recent if not s)
            rate = errors / len(recent)
            if rate > ALERT_ERROR_RATE_THRESHOLD:
                alert_error_rate(tool, rate, errors, len(recent))

    def error_rate(self, tool: str) -> Optional[float]:
        recent = self._calls.get(tool, [])
        if not recent:
            return None
        errors = sum(1 for _, s in recent if not s)
        return errors / len(recent)


# ── 告警发送（Sentry capture）─────────────────────────────
def _send_sentry(level: str, message: str, **context) -> None:
    """发 Sentry 告警（无 Sentry 客户端时退化为 log）。"""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in context.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(message, level=level)
    except ImportError:
        # Sentry SDK 不在（dev 环境），仅 log
        logger.warning(f"[ALERT:{level}] {message} | {context}")


def alert_restart_threshold(server_id: str, count: int) -> None:
    """Server restart 超阈值告警。"""
    _send_sentry(
        "error",
        f"MCP server {server_id!r} restarted {count} times in {ALERT_WINDOW_SECONDS}s",
        server_id=server_id,
        restart_count=count,
        window_seconds=ALERT_WINDOW_SECONDS,
    )


def alert_error_rate(tool: str, rate: float, errors: int, total: int) -> None:
    """Tool call 错误率超阈值告警。"""
    _send_sentry(
        "warning",
        f"MCP tool {tool!r} error rate {rate:.1%} ({errors}/{total}) exceeds {ALERT_ERROR_RATE_THRESHOLD:.0%}",
        tool=tool,
        error_rate=rate,
        errors=errors,
        total=total,
    )


def alert_destructive_failure(tool: str, error: str) -> None:
    """destructive capability tool 调用失败告警（业务关键）。"""
    _send_sentry(
        "error",
        f"Destructive tool {tool!r} failed: {error}",
        tool=tool,
        capability="destructive",
        error=error,
    )


# ── 全局单例 ─────────────────────────────────────────────────
restart_tracker = RestartTracker()
error_rate_tracker = ErrorRateTracker()
