"""业务事件 schema — 定义招聘业务流程的结构化事件。

使用方式:
    await event_emitter.emit(
        event_type=BusinessEventType.SCREENING_COMPLETED,
        entity_type="candidate",
        entity_id=candidate_id,
        domain_fields={"match_score": 0.85, "decision": "advance"},
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.agentops.core.schemas import BaseEvent


class BusinessEventType(StrEnum):
    """业务事件类型 — 与 EventType（系统级）分离，保持关注点独立。"""

    # 简历解析
    RESUME_PARSING_STARTED = "resume_parsing.started"
    RESUME_PARSING_COMPLETED = "resume_parsing.completed"
    RESUME_PARSING_FAILED = "resume_parsing.failed"

    # 候选人初筛
    SCREENING_STARTED = "screening.started"
    SCREENING_COMPLETED = "screening.completed"
    SCREENING_FAILED = "screening.failed"

    # JD 生成
    JD_GENERATION_STARTED = "jd.generation.started"
    JD_GENERATION_COMPLETED = "jd.generation.completed"
    JD_GENERATION_FAILED = "jd.generation.failed"

    # 面试安排
    INTERVIEW_SCHEDULED = "interview.scheduled"
    INTERVIEW_CANCELLED = "interview.cancelled"
    INTERVIEW_COMPLETED = "interview.completed"

    # 面试评估
    EVALUATION_STARTED = "evaluation.started"
    EVALUATION_COMPLETED = "evaluation.completed"
    EVALUATION_FAILED = "evaluation.failed"

    # P2-C Stage 11: 用户反馈
    FEEDBACK_SUBMITTED = "feedback.submitted"
    """用户/标注员/自动规则提交了一条反馈。"""


@dataclass(slots=True)
class BusinessEvent(BaseEvent):
    """业务事件 — 扩展 BaseEvent，添加业务领域字段。

    自动继承 BaseEvent 的 trace_id / span_id / parent_span_id / user_id / session_id，
    因此每个业务事件天然关联到 AgentOps 执行链路。
    """

    event_type: str = BusinessEventType.SCREENING_COMPLETED.value  # pyright: ignore[reportIncompatibleVariableOverride]

    # 业务实体标识
    entity_type: str = ""
    entity_id: str = ""

    # 领域数据域 — 结构化业务结果
    domain_fields: dict[str, Any] = field(default_factory=dict)

    # 覆盖 BaseEvent.name 的默认值生成
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.event_type
