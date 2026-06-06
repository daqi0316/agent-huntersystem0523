"""P5-7: HTTP metrics 中间件 — 记延迟 + 5xx 计数。"""
from __future__ import annotations

import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.telemetry import record_http_request

logger = logging.getLogger(__name__)


class PrometheusHTTPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start
            try:
                record_http_request(
                    method=request.method,
                    path=request.url.path,
                    status=status_code,
                    duration_seconds=duration,
                )
            except Exception as e:
                logger.warning("record_http_request failed: %s", e)
