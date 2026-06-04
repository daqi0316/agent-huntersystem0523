import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.rate_limit import create_rate_limit_middleware
from app.core.redis import close_redis
from app.core.qdrant import close_qdrant
from app.api.router import api_router
from app.agents.bootstrap import init_agents
from app.services.recommendation_scheduler import recommendation_scheduler_loop
from app.services.aggregation_service import aggregation_loop
import app.models  # noqa: F401  # 触发 model 注册到 Base.metadata，启动时 audit 可见

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v0.1.0", settings.app_name)

    # ── Schema 审计（防止 model enum/UUID 与 DB 不一致时静默 500）──
    # L2 启动期护栏：L1 编译期（pre-commit）+ 测试期（集成测试）失效时的兜底
    try:
        from app.core.schema_audit import audit_db_consistency, audit_required_tables
        await audit_db_consistency(fail_on_mismatch=True)
        logger.info("Schema audit passed")
    except RuntimeError as e:
        # 阻止启动：DB 与 model enum 不一致 = 必爆 500
        logger.error("Schema audit FAILED: %s", e)
        raise
    except Exception as e:
        # DB 连不上 / 其他非致命错误：仅 warn，不阻止启动（dev 早期允许）
        logger.warning("Schema audit skipped due to error: %s", e)

    # ── 必需表审计（model 声明的所有表必须在 DB 存在）──
    # 表缺失只 warn 不阻止启动（dashboard 端点会优雅降级返 mock），
    # 但聚合后台任务会拿不到表 → 需跑 `alembic upgrade head`。
    try:
        from app.core.schema_audit import audit_required_tables
        await audit_required_tables(fail_on_mismatch=False)
    except Exception as e:
        logger.warning("Required-tables audit skipped: %s", e)

    # ── 加载已启用的 MCP Server ──
    try:
        import json
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.mcp_server import MCPServer
        from app.mcp.manager import mcp_manager

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(MCPServer).where(MCPServer.enabled == True))
            servers = result.scalars().all()
            for s in servers:
                tools = json.loads(s.tools_cache) if s.tools_cache else None
                await mcp_manager.register(
                    server_id=s.id, name=s.name, url=s.server_url,
                    auth_type=s.auth_type, auth_token=s.auth_token or "",
                    tools_cache_data=tools,
                )
            if servers:
                logger.info("Loaded %d MCP server(s) from database", len(servers))
    except Exception as e:
        logger.warning("MCP server auto-load skipped: %s", e)

    # ── 初始化所有 Agent ──
    try:
        init_agents()
        logger.info("All specialist agents initialized and registered")
    except Exception as e:
        logger.error("Agent initialization failed: %s", e)

    # ── 启动推荐扫描定时器 ──
    scheduler_task = asyncio.create_task(recommendation_scheduler_loop())
    logger.info("Recommendation scheduler started in background")

    aggregation_task = asyncio.create_task(aggregation_loop())
    logger.info("Operation stats aggregation loop started in background")

    yield

    scheduler_task.cancel()
    aggregation_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        logger.info("Recommendation scheduler cancelled")
    try:
        await aggregation_task
    except asyncio.CancelledError:
        logger.info("Aggregation loop cancelled")
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


# ── Middleware (decorator-based — avoids Starlette #1334 BaseHTTPMiddleware) ──


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log each request method, path, status, and duration."""
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(create_rate_limit_middleware(limit=100, window=60))


# ── Unified error response ────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("%s %s → %s: %s", request.method, request.url.path, exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """将 Pydantic 校验错误（422）统一为 {success: false, error, details} 格式。"""
    errors = exc.errors()
    first_msg = errors[0]["msg"] if errors else "请求参数校验失败"
    logger.warning(
        "%s %s → 422: %s", request.method, request.url.path, first_msg
    )
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": first_msg,
            "details": [
                {"loc": e["loc"], "msg": e["msg"], "type": e["type"]}
                for e in errors
            ],
        },
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
