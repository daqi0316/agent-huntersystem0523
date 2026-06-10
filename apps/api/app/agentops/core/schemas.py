from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


SCHEMA_VERSION = "agentops.v1"


class EventType(StrEnum):
    TRACE_STARTED = "trace.started"
    TRACE_COMPLETED = "trace.completed"
    TRACE_FAILED = "trace.failed"
    SPAN_STARTED = "span.started"
    SPAN_COMPLETED = "span.completed"
    SPAN_FAILED = "span.failed"
    LLM_GENERATION_STARTED = "llm.generation.started"
    LLM_GENERATION_COMPLETED = "llm.generation.completed"
    LLM_GENERATION_FAILED = "llm.generation.failed"
    TOOL_INVOCATION_STARTED = "tool.invocation.started"
    TOOL_INVOCATION_COMPLETED = "tool.invocation.completed"
    TOOL_INVOCATION_FAILED = "tool.invocation.failed"
    EVAL_SCORE_CREATED = "eval.score.created"
    PRIVACY_REDACTION_APPLIED = "privacy.redaction.applied"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class BaseEvent:
    name: str
    event_type: EventType = EventType.SPAN_STARTED
    schema_version: str = SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=_utc_now_iso)
    environment: str = ""
    service: str = "api"
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    tenant_id: str = ""
    user_id: str = ""
    session_id: str = ""
    request_id: str = ""
    operation_id: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    input: JsonValue = None
    output: JsonValue = None
    error: str = ""

    def to_dict(self) -> dict[str, JsonValue]:
        data = asdict(self)
        data["event_type"] = self.event_type.value
        return data


@dataclass(slots=True)
class TraceEvent(BaseEvent):
    event_type: EventType = EventType.TRACE_STARTED


@dataclass(slots=True)
class SpanEvent(BaseEvent):
    event_type: EventType = EventType.SPAN_STARTED
    duration_ms: float | None = None


@dataclass(slots=True)
class LLMGenerationEvent(BaseEvent):
    event_type: EventType = EventType.LLM_GENERATION_STARTED
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    parameters: dict[str, JsonValue] = field(default_factory=dict)
    duration_ms: float | None = None


@dataclass(slots=True)
class ToolInvocationEvent(BaseEvent):
    event_type: EventType = EventType.TOOL_INVOCATION_STARTED
    tool_name: str = ""
    tool_category: str = ""
    success: bool | None = None
    retry_count: int = 0
    needs_human: bool = False
    duration_ms: float | None = None


@dataclass(slots=True)
class ScoreEvent(BaseEvent):
    event_type: EventType = EventType.EVAL_SCORE_CREATED
    score_name: str = ""
    value: float | int | bool | str | None = None
    comment: str = ""
    source: str = "system"
    evaluator_version: str = ""
    rubric_version: str = ""
