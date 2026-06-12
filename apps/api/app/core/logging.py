"""F19: 集中日志配置 — structlog 跨服务统一字段 (graceful degradation).

momus §3.3 标准字段: ts/level/service/trace_id/span_id/user_id/org_id/path/latency_ms/status.

structlog 未装时 fallback 标准 logging (API 一致, 装后自动升级).

用法:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("request_completed", path="/api/v1/auth/login", latency_ms=42, status=200)
"""
from __future__ import annotations

import logging
import sys
from typing import Any

try:
    import structlog
    _STRUCTLOG_AVAILABLE = True
except ImportError:
    _STRUCTLOG_AVAILABLE = False


def setup_logging(service: str = "api", level: str = "INFO") -> None:
    """F19: 配 structlog JSON 输出 (未装时 fallback 标准 logging)."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    if not _STRUCTLOG_AVAILABLE:
        logging.basicConfig(
            format=f"%(asctime)s {service} %(levelname)s %(name)s %(message)s",
            stream=sys.stdout,
            level=log_level,
            force=True,
        )
        return

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            structlog.processors.StackInfoRenderer(),
            _add_service(service),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )


def _add_service(service: str):
    def processor(_: Any, __: str, event_dict: dict) -> dict:
        event_dict.setdefault("service", service)
        return event_dict
    return processor


def get_logger(name: str | None = None) -> Any:
    """F19: 装 structlog 返 BoundLogger, 未装返 stdlib logger (API 一致)."""
    if _STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    return logging.getLogger(name or "app")
