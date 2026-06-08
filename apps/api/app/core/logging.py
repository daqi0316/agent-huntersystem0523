"""F19: 集中日志配置 — structlog 跨服务统一字段.

momus §3.3 标准字段: ts/level/service/trace_id/span_id/user_id/org_id/path/latency_ms/status.

用法:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("request_completed", path="/api/v1/auth/login", latency_ms=42, status=200)
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def setup_logging(service: str = "api", level: str = "INFO") -> None:
    """F19: 配 structlog JSON 输出到 stdout, 跨服务统一字段.

    标准字段 (momus §3.3):
    - ts (ISO timestamp)
    - level (DEBUG/INFO/WARNING/ERROR)
    - service (api/mcp/worker/...)
    - event (msg 字段)
    - trace_id, span_id, user_id, org_id, path, latency_ms, status (业务字段)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
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


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
