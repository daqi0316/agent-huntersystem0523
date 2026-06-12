"""P2-C Stage 11: 用户反馈与人工标注 — 可扩展反馈系统。

设计原则:
- 多态反馈: 不止 👍/👎，支持 category + score 结构化反馈
- 分层可扩展: 枚举值加即用，无需改 schema
- 链路关联: 每个反馈关联 trace_id / span_id / message_id
- 来源可追溯: end_user / annotator / auto_rule / auto_eval
- 事件驱动: 反馈创建通过 EventEmitter 写入 agentops event stream
"""

from app.agentops.feedback.models import AgentFeedbackModel
from app.agentops.feedback.schemas import (
    FeedbackCategory,
    FeedbackCreate,
    FeedbackResponse,
    FeedbackSource,
    FeedbackStats,
    FeedbackTarget,
    FeedbackUpdate,
)
from app.agentops.feedback.service import FeedbackService

__all__ = [
    "AgentFeedbackModel",
    "FeedbackCategory",
    "FeedbackCreate",
    "FeedbackResponse",
    "FeedbackSource",
    "FeedbackStats",
    "FeedbackTarget",
    "FeedbackUpdate",
    "FeedbackService",
]
