"""租户级治理策略 (P2-C Stage 13).

支持按租户覆盖采样率、脱敏级别、保留等配置。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TenantConfig:
    """单个租户的配置覆盖。

    Attributes:
        tenant_id: 租户标识。
        sampling_rate: 覆盖的采样率 (None = 使用全局默认)。
        privacy_level: 脱敏级别 (strict/normal/relaxed, None = 全局默认)。
        retention_days: 覆盖的保留天数 (None = 全局默认)。
        tags: 标签列表。
        notes: 备注。
    """

    tenant_id: str
    sampling_rate: float | None = None
    privacy_level: str | None = None
    retention_days: int | None = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.sampling_rate is not None:
            self.sampling_rate = max(0.0, min(1.0, self.sampling_rate))


@dataclass(slots=True)
class TenantPolicy:
    """租户策略集合。"""

    tenants: dict[str, TenantConfig] = field(default_factory=dict)

    def get(self, tenant_id: str) -> TenantConfig | None:
        return self.tenants.get(tenant_id)

    def set(self, config: TenantConfig) -> None:
        self.tenants[config.tenant_id] = config

    def remove(self, tenant_id: str) -> bool:
        return self.tenants.pop(tenant_id, None) is not None

    def list(self) -> list[TenantConfig]:
        return list(self.tenants.values())

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {
            tid: {
                "sampling_rate": tc.sampling_rate,
                "privacy_level": tc.privacy_level,
                "retention_days": tc.retention_days,
                "tags": tc.tags,
                "notes": tc.notes,
            }
            for tid, tc in self.tenants.items()
        }


class TenantPolicyStore:
    """租户策略存储（默认 in-memory，可扩展为 DB 存储）。"""

    def __init__(self) -> None:
        self._policy = TenantPolicy()

    @property
    def policy(self) -> TenantPolicy:
        return self._policy

    def get(self, tenant_id: str) -> TenantConfig | None:
        return self._policy.get(tenant_id)

    def set(self, config: TenantConfig) -> None:
        self._policy.set(config)

    def remove(self, tenant_id: str) -> bool:
        return self._policy.remove(tenant_id)

    def list(self) -> list[TenantConfig]:
        return self._policy.list()
