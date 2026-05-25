import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.rate_limit import RateLimitMiddleware
from app.core.redis import close_redis
from app.core.qdrant import close_qdrant
from app.api.router import api_router

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start
        logger.info(
            "%s %s → %s (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed * 1000,
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v0.1.0", settings.app_name)
    yield
    await close_redis()
    await close_qdrant()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, limit=100, window=60)


# ── Unified error response ────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("%s %s → %s: %s", request.method, request.url.path, exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    from app.core.config import settings as s

    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    content: dict[str, object] = {"success": False, "error": "Internal server error"}
    if s.debug:
        content["debug"] = str(exc)
    return JSONResponse(status_code=500, content=content)


app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ai-recruitment-api"}


@app.get("/metrics")
async def metrics():
    """基础 Prometheus-style 指标（不含 prometheus_client 时返回存活信号）。"""
    from app.core.redis import redis_client

    redis_ok = False
    try:
        await redis_client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "service": settings.app_name,
        "version": "2.0.0",
        "uptime_seconds": 0,
        "redis_connected": redis_ok,
    }
