"""Dataset Pydantic schemas — 定义 dataset item 的结构与校验。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DatasetItemCategory(StrEnum):
    """Dataset item 分类 — 与招聘业务场景对齐。"""

    RESUME_PARSE = "resume_parse"
    SCREENING = "screening"
    JD_GENERATION = "jd_generation"
    INTERVIEW_SCHEDULING = "interview_scheduling"
    CONVERSATION = "conversation"
    TOOL_CALL = "tool_call"
    OTHER = "other"


class DatasetItemSource(StrEnum):
    """Dataset item 的来源。"""

    BAD_CASE = "bad_case"           # 用户差评 → dataset item
    SYSTEM_FAILURE = "system_failure"  # 系统失败 → dataset item
    ANNOTATION = "annotation"       # 人工标注 → dataset item
    MANUAL = "manual"               # 手动创建
    SAMPLED = "sampled"             # 线上采样
    OTHER = "other"


class DatasetItemCreate(BaseModel):
    """创建 dataset item 的请求。"""

    category: DatasetItemCategory = DatasetItemCategory.OTHER
    source: DatasetItemSource = DatasetItemSource.MANUAL

    # 原始执行链路关联
    trace_id: str = ""
    span_id: str = ""
    session_id: str = ""

    # 业务实体关联
    entity_type: str = ""
    entity_id: str = ""

    # 核心数据 — 快照与元数据
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    expected_output: dict[str, Any] = Field(default_factory=dict)
    actual_output: dict[str, Any] = Field(default_factory=dict)

    # 反馈关联（若从 feedback 生成，记录对应的 feedback_id）
    feedback_id: str = ""

    # 标签与标记
    tags: list[str] = Field(default_factory=list, max_length=20)
    is_bad_case: bool = False
    description: str = ""

    # 可选 — 人工标注的修正
    corrected_output: dict[str, Any] | None = None
    correction_notes: str = ""

    # 评分与优先级
    priority: int = Field(default=0, ge=0, le=5)  # 0=normal, 5=critical
    score: float = Field(default=0.0, ge=0.0, le=1.0)

    # 自由元数据
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetItemResponse(BaseModel):
    """Dataset item 响应。"""

    id: str
    category: str
    source: str

    trace_id: str
    span_id: str
    session_id: str

    entity_type: str
    entity_id: str

    input_snapshot: dict[str, Any]
    expected_output: dict[str, Any]
    actual_output: dict[str, Any]

    feedback_id: str

    tags: list[str]
    is_bad_case: bool
    description: str

    corrected_output: dict[str, Any] | None
    correction_notes: str

    priority: int
    score: float
    metadata: dict[str, Any]

    created_at: str
    updated_at: str


class DatasetStats(BaseModel):
    """Dataset 统计。"""

    total_count: int
    category_counts: dict[str, int]
    source_counts: dict[str, int]
    bad_case_count: int
    recent_items: int = 0  # 最近 7 天新增


class DatasetListResponse(BaseModel):
    """分页查询响应。"""

    items: list[DatasetItemResponse]
    total: int
    limit: int
    offset: int
