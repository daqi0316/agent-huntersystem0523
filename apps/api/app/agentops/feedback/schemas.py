"""反馈系统 Pydantic schema — 请求/响应/统计。

设计原则:
- FeedbackCategory: 枚举可扩展，加值即用不改 schema
- FeedbackSource: 区分来源，为 Stage 12 dataset 创建打好基础
- FeedbackTarget: 可选关联 trace / span / message / session
- Score: float [0.0, 1.0]，0.0 最差，1.0 最好
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FeedbackCategory(StrEnum):
    """反馈类别 — 枚举可扩展。"""

    RELEVANCE = "relevance"
    """回答相关性：输出是否命中用户问题核心。"""
    ACCURACY = "accuracy"
    """答案准确性：事实是否正确。"""
    COMPLETENESS = "completeness"
    """完整度：是否遗漏关键信息。"""
    TONE = "tone"
    """语气/风格：沟通方式是否合适。"""
    TOOL_CORRECTNESS = "tool_call"
    """工具调用正确性：Agent 选择了正确的工具和参数。"""
    QUALITY = "quality"
    """综合质量：用户对此次交互的整体满意度。"""
    CUSTOM = "custom"
    """自定义类别：由 tags 或 metadata 进一步细分。"""


class FeedbackSource(StrEnum):
    """反馈来源 — 为 Stage 12/13 预留扩展。"""

    END_USER = "end_user"
    """最终用户在 UI 上提交的反馈。"""
    ANNOTATOR = "annotator"
    """人工标注员在审核界面提交的标注。"""
    AUTO_RULE = "auto_rule"
    """自动规则触发的 bad_case 标记。"""
    AUTO_EVALUATOR = "auto_eval"
    """LLM Judge 自动评估产生的反馈。"""


class FeedbackTarget(BaseModel):
    """反馈定位目标 — 关联到 AgentOps 执行链路中的哪个节点。"""

    trace_id: str | None = Field(None, description="AgentOps trace ID")
    span_id: str | None = Field(None, description="AgentOps span ID")
    message_id: str | None = Field(None, description="对话消息 ID")
    session_id: str | None = Field(None, description="对话会话 ID")
    entity_type: str | None = Field(None, description="业务实体类型（如 candidate, interview）")
    entity_id: str | None = Field(None, description="业务实体 ID")


class FeedbackCreate(BaseModel):
    """创建反馈请求。"""

    category: FeedbackCategory = Field(..., description="反馈类别")
    score: float = Field(..., ge=0.0, le=1.0, description="评分 [0.0, 1.0]")
    reason: str | None = Field(None, max_length=2000, description="反馈理由")
    target: FeedbackTarget = Field(default_factory=FeedbackTarget, description="关联的执行链路节点")
    source: FeedbackSource = Field(default=FeedbackSource.END_USER, description="反馈来源")
    tags: list[str] = Field(default_factory=list, max_length=10, description="标签列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")

    @field_validator("reason")
    @classmethod
    def reason_not_empty_string(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            return None
        return v


class FeedbackUpdate(BaseModel):
    """更新反馈请求（标注审核用）。"""

    category: FeedbackCategory | None = None
    score: float | None = Field(None, ge=0.0, le=1.0)
    reason: str | None = None
    source: FeedbackSource | None = None
    tags: list[str] | None = None


class FeedbackResponse(BaseModel):
    """反馈响应。"""

    id: str
    category: str
    source: str
    score: float
    reason: str = ""
    trace_id: str = ""
    span_id: str = ""
    message_id: str = ""
    session_id: str = ""
    target_entity_type: str = ""
    target_entity_id: str = ""
    user_id: str = ""
    tags: list[str] = []
    created_at: str = ""
    updated_at: str = ""


class FeedbackStats(BaseModel):
    """反馈聚合统计。"""

    total_count: int = 0
    overall_avg_score: float = 0.0
    category_stats: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="按 category 聚合: {category: {avg_score: float, count: int}}",
    )


class FeedbackListResponse(BaseModel):
    """反馈列表响应。"""

    items: list[FeedbackResponse]
    total: int
    skip: int = 0
    limit: int = 50
