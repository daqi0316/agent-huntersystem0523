"""A/B 灰度管理 API（v4 PR-1b）。

端点：
  GET  /api/v1/mcp/ab         — 当前 config + 实时状态
  PATCH /api/v1/mcp/ab        — 改 percent / enabled（hot-reload）
  POST /api/v1/mcp/ab/reload  — 从 env 重新加载
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.mcp.ab_router import (
    get_config,
    reload_from_env,
    set_new_path_health,
    update_percent,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mcp/ab", tags=["MCP A/B Routing (v4 PR-1b)"])


class ABConfigUpdate(BaseModel):
    percent: int | None = Field(default=None, ge=0, le=100)
    enabled: bool | None = None


@router.get("")
async def get_ab_status() -> dict[str, Any]:
    """当前 A/B config + 实时状态。"""
    cfg = get_config()
    return {
        "enabled": cfg.enabled,
        "percent": cfg.percent,
        "allowlist": list(cfg.allowlist),
        "metrics_hint": "prometheus: ab_decisions_total / ab_calls_total / ab_call_duration_seconds / ab_current_percent",
    }


@router.patch("")
async def update_ab_config(update: ABConfigUpdate) -> dict[str, Any]:
    """改 percent / enabled（hot-reload，不重启 host）。"""
    if update.percent is None and update.enabled is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if update.percent is not None:
        update_percent(update.percent, enabled=update.enabled)
    elif update.enabled is not None:
        update_percent(cfg_percent := get_config().percent, enabled=update.enabled)
    cfg = get_config()
    return {
        "enabled": cfg.enabled,
        "percent": cfg.percent,
        "message": "Updated (no restart needed)",
    }


@router.post("/reload")
async def reload_ab_config() -> dict[str, Any]:
    """从 env 重新加载 config。"""
    reload_from_env()
    cfg = get_config()
    return {
        "enabled": cfg.enabled,
        "percent": cfg.percent,
        "allowlist": list(cfg.allowlist),
        "source": "env",
    }


@router.post("/new-path-health")
async def report_new_path_health(tool: str, up: bool) -> dict[str, Any]:
    """外部 health check 报告 new path 健康状态。"""
    set_new_path_health(tool, up)
    return {"tool": tool, "up": up}
