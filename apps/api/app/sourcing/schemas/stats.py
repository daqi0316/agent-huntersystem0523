from typing import Any

from pydantic import BaseModel


class SourcingStats(BaseModel):
    total_tasks: int
    total_candidates: int
    success_rate: float
    platform_stats: dict[str, Any]
    daily_stats: list[dict[str, Any]]


class HealthStatus(BaseModel):
    platforms: dict[str, Any]
    accounts: dict[str, Any]
    proxy_pool: dict[str, int]
    queue_depth: int
