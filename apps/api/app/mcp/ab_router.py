"""A/B 灰度路由器（v4 PR-1b 灰度切流）。

设计原则（工程化 — 不是简单 if-else）：
  1. **Sticky routing**：同一 user_id 始终走同一 path（hash 一致）
  2. **Allowlist bypass**：admin / 测试用户强制走 new path（验证）
  3. **Fallback on error**：new path 失败自动 fallback 到 old path + 记录
  4. **Hot-reload percent**：env var + 内存配置双写，admin endpoint 改
  5. **独立 metrics**：ab_* 指标，可视化对比 old/new
  6. **Kill switch**：NEW_PATH_UP=False 强制全走 old path

控制参数：
  - env MCP_AB_ENABLED=true|false（master switch）
  - env MCP_AB_PERCENT=10（默认 10% 走 new path）
  - env MCP_AB_ALLOWLIST=user_id1,user_id2（强制走 new path）
  - admin endpoint PATCH /api/v1/mcp/ab 改 percent
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.mcp.ab_metrics import (
    record_call,
    record_decision,
    set_new_path_up,
    set_percent,
)

logger = logging.getLogger(__name__)


# ── 全局配置（进程内可热改）────────────────────────────────────
@dataclass
class ABConfig:
    enabled: bool = False
    percent: int = 0
    allowlist: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> "ABConfig":
        return cls(
            enabled=os.getenv("MCP_AB_ENABLED", "false").lower() == "true",
            percent=int(os.getenv("MCP_AB_PERCENT", "0")),
            allowlist=tuple(
                uid.strip()
                for uid in os.getenv("MCP_AB_ALLOWLIST", "").split(",")
                if uid.strip()
            ),
        )


_config = ABConfig.from_env()


def get_config() -> ABConfig:
    return _config


def reload_from_env() -> None:
    """从 env 重新加载（admin endpoint 调或 watcher 调）。"""
    global _config
    _config = ABConfig.from_env()
    # 同步 metric
    set_percent("*", _config.percent)
    logger.info("A/B config reloaded: enabled=%s percent=%d", _config.enabled, _config.percent)


def update_percent(percent: int, enabled: bool | None = None) -> None:
    """admin 改 percent（hot-reload，不重启 host）。"""
    global _config
    _config = ABConfig(
        enabled=enabled if enabled is not None else _config.enabled,
        percent=max(0, min(100, percent)),
        allowlist=_config.allowlist,
    )
    set_percent("*", _config.percent)
    logger.info("A/B percent updated: percent=%d enabled=%s", _config.percent, _config.enabled)


# ── Sticky hash ─────────────────────────────────────────────────
def _bucket(user_id: str, tool: str) -> int:
    """同一 (user_id, tool) 永远在同一 bucket（0-99）。

    用 SHA256 避免 Python hash() 跨进程不一致。
    """
    h = hashlib.sha256(f"{user_id}:{tool}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


# ── 路由决策 ─────────────────────────────────────────────────
def _decide_path(user_id: str, tool: str) -> str:
    """返回 "new" 或 "old"。

    优先级：
      1. allowlist 命中 → "new"（reason=allowlist）
      2. percent=0 → "old"
      3. percent=100 → "new"（reason=percent）
      4. hash bucket < percent → "new"（reason=hash_bucket）
      5. else "old"
    """
    cfg = get_config()
    if not cfg.enabled:
        return "old"
    if user_id and user_id in cfg.allowlist:
        record_decision(tool, "new", "allowlist")
        return "new"
    if cfg.percent == 0:
        record_decision(tool, "old", "percent_zero")
        return "old"
    if cfg.percent == 100:
        record_decision(tool, "new", "percent_hundred")
        return "new"
    bucket = _bucket(user_id or "anonymous", tool)
    if bucket < cfg.percent:
        record_decision(tool, "new", "hash_bucket")
        return "new"
    record_decision(tool, "old", "hash_bucket")
    return "old"


# ── 包装 handler ─────────────────────────────────────────────
def ab_wrap_handler(
    tool: str,
    old_handler: Callable[..., Any],
    new_handler: Callable[..., Awaitable[Any]],
    *,
    new_path_up: bool = True,
) -> Callable[..., Awaitable[Any]]:
    """包一个旧 + 新 handler，返回 router-aware async handler。

    调用时：
      1. 决策 path（_decide_path）
      2. 调对应 handler，记录 latency + status
      3. new path 失败 → fallback old（record fallback_used status）
    """
    set_new_path_up(tool, new_path_up)

    async def wrapper(*args, user_id: str | None = None, **kwargs) -> Any:
        # agent_service 调 handler(**args) — 不传 user_id
        # 我们用 stack inspect 或 fallback user_id
        actual_user_id = user_id or _extract_user_id_from_args(args, kwargs)
        path = _decide_path(actual_user_id, tool)
        # 实际可调用性检查（如果 new_path down 强制 old）
        if path == "new" and not new_path_up:
            path = "old"
            record_decision(tool, "old", "new_path_down")

        start = time.time()
        try:
            if path == "new":
                result = await new_handler(*args, **kwargs)
            else:
                result = await _invoke_old(old_handler, *args, **kwargs)
            duration = time.time() - start
            record_call(tool, path, "success", duration)
            return result
        except Exception as e:
            duration = time.time() - start
            logger.warning("A/B %s path=%s failed: %s", tool, path, e)
            if path == "new":
                # Fallback to old
                try:
                    result = await _invoke_old(old_handler, *args, **kwargs)
                    fallback_duration = time.time() - start
                    record_call(tool, "new", "fallback_used", fallback_duration)
                    record_call(tool, "old", "success", 0)
                    return result
                except Exception as e2:
                    duration = time.time() - start
                    record_call(tool, "new", "error", duration)
                    raise
            else:
                record_call(tool, path, "error", duration)
                raise

    wrapper.__name__ = f"ab_wrapped_{tool}"
    wrapper.__doc__ = f"A/B router for {tool} (percent={get_config().percent})"
    return wrapper


async def _invoke_old(old_handler: Callable, *args, **kwargs) -> Any:
    """调旧 handler（同步或异步）。"""
    result = old_handler(*args, **kwargs)
    if asyncio.iscoroutine(result):
        result = await result
    return result


def _extract_user_id_from_args(args: tuple, kwargs: dict) -> str | None:
    """从 handler 调用参数里尝试提取 user_id（heuristic）。

    agent_service.chat_with_tools(messages, user_id=..., ...) 把 user_id 当 keyword
    传，但我们包装的 wrapper 是 handler(**tool_args) — 不含 user_id。
    实际：user_id 没法从 handler 调用栈拿到，依赖调用方通过 **kwargs 传。
    """
    return kwargs.pop("_ab_user_id", None) or None


def set_new_path_health(tool: str, up: bool) -> None:
    """外部调（如 health check）报告 new path 是否健康。"""
    set_new_path_up(tool, up)
