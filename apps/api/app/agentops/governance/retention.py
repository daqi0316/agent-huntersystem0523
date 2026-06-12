"""数据保留策略 (P2-C Stage 13).

定义按环境的保留天数，支持 incident 保留时长覆盖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RetentionConfig:
    """数据保留配置。

    Attributes:
        dev_days: 开发环境保留天数 (默认 7)。
        staging_days: 预发布环境保留天数 (默认 30)。
        prod_days: 生产环境保留天数 (默认 180)。
        incident_days: 事故/异常 trace 保留天数 (默认 730)。
    """

    dev_days: int = 7
    staging_days: int = 30
    prod_days: int = 180
    incident_days: int = 730

    def __post_init__(self) -> None:
        for attr in ("dev_days", "staging_days", "prod_days", "incident_days"):
            val = getattr(self, attr)
            if val < 0:
                object.__setattr__(self, attr, 0)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetentionConfig:
        """从 dict 创建配置。"""
        return cls(
            dev_days=data.get("dev_days", 7),
            staging_days=data.get("staging_days", 30),
            prod_days=data.get("prod_days", 180),
            incident_days=data.get("incident_days", 730),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "dev_days": self.dev_days,
            "staging_days": self.staging_days,
            "prod_days": self.prod_days,
            "incident_days": self.incident_days,
        }


_ENV_MAP: dict[str, str] = {
    "dev": "dev_days",
    "development": "dev_days",
    "staging": "staging_days",
    "stage": "staging_days",
    "prod": "prod_days",
    "production": "prod_days",
}


def get_retention_days(
    config: RetentionConfig,
    environment: str,
    *,
    is_incident: bool = False,
) -> int:
    """获取指定环境的保留天数。

    Args:
        config: 保留配置。
        environment: 环境名称 (dev/development/staging/stage/prod/production)。
        is_incident: 是否为事故 trace。

    Returns:
        保留天数。
    """
    if is_incident:
        return config.incident_days

    attr = _ENV_MAP.get(environment.lower())
    if attr is None:
        return config.dev_days  # 未知环境默认 dev
    return getattr(config, attr)
