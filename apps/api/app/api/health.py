"""健康检查端点 — 启动期 schema audit 的运行时查询接口。

L2 启动期护栏的运行时扩展：前端/监控可调 ``/api/v1/health/schema`` 看到
当前 DB 状态（缺失表、enum 漂移），不必重启服务。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.config import settings
from app.core.response import success

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/health/schema")
async def health_schema():
    """Schema 健康检查 — **永远 200**（不引入新 bug）。

    失败兜底：audit 内部抛任何异常都返 ``status="degraded"`` 而非 500。
    防止 health 端点本身崩溃复现"无法连接后端服务"问题。

    信息粒度：
    - settings.debug=True：返完整 missing_tables + enum_drift
    - 生产模式：仅返 ``status`` 字段（不暴露内部状态）
    """
    try:
        from app.core.schema_audit import audit_db_consistency, audit_required_tables

        missing = await audit_required_tables(fail_on_mismatch=False)
        drift = await audit_db_consistency(fail_on_mismatch=False)
    except Exception:
        logger.exception("health/schema audit crashed; returning degraded")
        return success({"status": "degraded", "error": "audit_unavailable"})

    payload: dict = {"status": "ok" if not (missing or drift) else "degraded"}
    if settings.debug:
        payload["missing_tables"] = missing
        payload["enum_drift"] = drift
    return success(payload)
