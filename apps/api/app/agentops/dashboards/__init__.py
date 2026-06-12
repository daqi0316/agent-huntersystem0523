"""AgentOps 看板与产品化 (P2-C Stage 14).

提供 metrics 聚合和 REST API，支撑前端 Debug Console、质量看板、成本看板。
"""
from __future__ import annotations

from .metrics import DashboardMetrics

__all__ = [
    "DashboardMetrics",
]
