"""Experiment Pydantic schemas — 定义实验结构与校验。

Experiment = 一次测试方案（基于哪些 dataset items + 什么评估方法）
ExperimentRun = 一次实验执行结果
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExperimentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentCreate(BaseModel):
    """创建实验的请求。"""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    dataset_item_ids: list[str] = Field(default_factory=list, max_length=1000)

    # 评估方法配置
    evaluator_type: str = "rule_based"  # rule_based | llm_judge | comparison
    evaluator_config: dict[str, Any] = Field(default_factory=dict)

    # 待比较的配置变体
    variants: list[dict[str, Any]] = Field(
        default_factory=list, max_length=10,
        description="配置变体列表，每个变体是一个 dict，如 {'prompt_version': 'v2', 'model': 'gpt-4'}",
    )
    tags: list[str] = Field(default_factory=list, max_length=20)


class ExperimentResponse(BaseModel):
    """实验响应。"""

    id: str
    name: str
    description: str
    status: str
    dataset_item_ids: list[str]

    evaluator_type: str
    evaluator_config: dict[str, Any]

    variants: list[dict[str, Any]]
    tags: list[str]

    created_by: str
    created_at: str
    updated_at: str


class ExperimentRunCreate(BaseModel):
    """触发实验执行的请求。"""

    experiment_id: str
    variant_index: int = Field(default=0, ge=0, description="当前运行使用第几个 variant")


class ExperimentRunResponse(BaseModel):
    """单次实验运行的结果。"""

    id: str
    experiment_id: str
    variant_index: int

    status: str
    total_items: int
    passed_items: int
    failed_items: int
    avg_score: float

    results: list[dict[str, Any]]

    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0

    error_message: str = ""


class ExperimentRunSummaryResponse(BaseModel):
    """实验运行摘要（列表用）。"""

    id: str
    experiment_id: str
    variant_index: int
    status: str
    total_items: int
    passed_items: int
    avg_score: float
    started_at: str
    completed_at: str
    duration_ms: float


class ExperimentListResponse(BaseModel):
    """实验列表响应。"""

    experiments: list[ExperimentResponse]
    total: int
    limit: int
    offset: int


class VariantComparison(BaseModel):
    """单 variant 的对比结果。"""

    variant_index: int
    variant_config: dict[str, Any] = Field(default_factory=dict)
    avg_score: float = 0.0
    total_items: int = 0
    passed_items: int = 0
    failed_items: int = 0
    duration_ms: float = 0.0
    run_id: str = ""
    status: str = ""


class ExperimentComparisonResponse(BaseModel):
    """多 variant 对比响应。"""

    experiment_id: str
    experiment_name: str
    best_variant_index: int = 0
    best_score: float = 0.0
    score_delta: float = 0.0
    comparisons: list[VariantComparison] = Field(default_factory=list)
