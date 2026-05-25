"""Rate limiting middleware — in-memory token bucket with optional Redis backend."""

import asyncio
import logging
import time
from collections import defaultdict

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class InMemoryRateStore:
    """ per-process in-memory rate counter.
    
    Not shared across replicas — suitable for single-instance deployments
    or development. Replace with RedisStore for production multi-replica setups.
    """

    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def _prune(self, key: str, window: float) -> None:
        now = time.monotonic()
        cutoff = now - window
        self._buckets[key] = [t for t in self._buckets[key] if t > cutoff]

    def check(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        """Check if key is within rate limit.

        Returns (allowed: bool, remaining: int).
        """
        self._prune(key, window)
        current = len(self._buckets[key])
        if current >= limit:
            return False, 0
        self._buckets[key].append(time.monotonic())
        return True, limit - current - 1

    def remaining(self, key: str, limit: int, window: float) -> int:
        self._prune(key, window)
        return max(0, limit - len(self._buckets[key]))

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


_store = InMemoryRateStore()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for per-IP rate limiting.

    Usage in app.main.py:
        app.add_middleware(RateLimitMiddleware, limit=100, window=60)

    To configure per-route limits, override the route's app.state or pass
    custom limits via the request object in a route handler.
    """

    def __init__(
        self,
        app,
        limit: int = 100,
        window: int = 60,
        exclude_paths: tuple[str, ...] = ("/health", "/metrics", "/docs", "/redoc", "/openapi.json"),
    ):
        super().__init__(app)
        self.default_limit = limit
        self.default_window = window
        self.exclude_paths = exclude_paths

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths or request.url.path.startswith("/docs") or request.url.path.startswith("/redoc"):
            return await call_next(request)

        # Use client IP + path as rate limit key
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{request.url.path}"
        limit = self.default_limit
        window = self.default_window

        allowed, remaining = _store.check(key, limit, window)
        if not allowed:
            logger.warning("Rate limit exceeded for %s (limit=%d/%ds)", key, limit, window)
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": "Too many requests. Please try again later."},
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
