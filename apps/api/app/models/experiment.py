"""P6-7: A/B 测试框架 — experiments + assignments + events 表 + 显著性分析。

分配: user_id hash 取模 0-100, 落到 variant.traffic_pct 区间。
显著性: 简化 z-test for proportions (Phase 6 真实数据后用 chi-square 替代)。
"""
from __future__ import annotations

import enum
import hashlib
import math
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class ExperimentStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ExperimentEvent(str, enum.Enum):
    IMPRESSION = "impression"
    CONVERSION = "conversion"


MIN_SAMPLE_SIZE = 30
SIGNIFICANCE_Z = 1.96


class Experiment(Base):
    __tablename__ = "experiment"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[ExperimentStatus] = mapped_column(
        SAEnum(ExperimentStatus, name="experiment_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=ExperimentStatus.DRAFT,
    )
    variants: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]",
    )
    primary_metric: Mapped[str] = mapped_column(String(64), nullable=False, server_default="conversion")
    target_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignment"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    variant: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class ExperimentEvent_(Base):
    __tablename__ = "experiment_event"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    variant: Mapped[str] = mapped_column(String(32), nullable=False)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


def assign_variant(
    user_key: str, experiment_name: str, variants: list[dict]
) -> Optional[str]:
    """按 user_key 哈希分配到 variants 区间 (按 traffic_pct 累加)。

    variants 格式: [{"name": "A", "traffic_pct": 50, "config": {...}}, {"name": "B", "traffic_pct": 50, ...}]
    返 variant name 或 None (不在实验范围内)。
    """
    if not variants:
        return None
    h = hashlib.md5(f"{experiment_name}:{user_key}".encode("utf-8")).hexdigest()
    bucket = int(h[:8], 16) % 100
    cumulative = 0
    for v in variants:
        cumulative += int(v.get("traffic_pct", 0))
        if bucket < cumulative:
            return v["name"]
    return None


def z_test_two_proportions(
    p1_conv: int, p1_total: int,
    p2_conv: int, p2_total: int,
) -> tuple[float, float]:
    """返 (z_score, p_value_approx)。p < 0.05 = 显著。"""
    if p1_total < MIN_SAMPLE_SIZE or p2_total < MIN_SAMPLE_SIZE:
        return 0.0, 1.0
    p1 = p1_conv / p1_total
    p2 = p2_conv / p2_total
    p_pool = (p1_conv + p2_conv) / (p1_total + p2_total)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / p1_total + 1 / p2_total))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    p_val = 2 * (1 - _normal_cdf(abs(z)))
    return z, p_val


def _normal_cdf(z: float) -> float:
    """标准正态分布 CDF 近似 (Abramowitz & Stegun)。"""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))
