"""
健康检查端点 — 查询引擎管理器状态
"""
from __future__ import annotations

from ..manager.engine_manager import EngineManager


async def get_engine_health() -> dict:
    """
    引擎健康检查
    返回所有已创建引擎的健康状态
    """
    manager = EngineManager()
    health_results = await manager.health_check_all()

    return {
        "engines": {
            k.value if hasattr(k, "value") else str(k): v.value
            for k, v in health_results.items()
        },
        "total_engines": len(health_results),
        "available": sum(
            1 for v in health_results.values()
            if v.value == "available"
        ),
    }


__all__ = ["get_engine_health"]
