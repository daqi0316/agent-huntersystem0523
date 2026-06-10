from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class AgentOpsContext:
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    user_id: str = ""
    tenant_id: str = ""
    session_id: str = ""
    request_id: str = ""
    operation_id: str = ""
    environment: str = ""
    service: str = "api"

    def child(self, *, span_id: str = "", parent_span_id: str | None = None) -> AgentOpsContext:
        return replace(
            self,
            span_id=span_id or self.span_id,
            parent_span_id=self.span_id if parent_span_id is None else parent_span_id,
        )


_current_context: ContextVar[AgentOpsContext | None] = ContextVar("agentops_context", default=None)


def get_context() -> AgentOpsContext | None:
    return _current_context.get()


def set_context(context: AgentOpsContext | None) -> Token[AgentOpsContext | None]:
    return _current_context.set(context)


def reset_context(token: Token[AgentOpsContext | None]) -> None:
    _current_context.reset(token)


def clear_context() -> None:
    _ = _current_context.set(None)


@contextmanager
def use_context(context: AgentOpsContext) -> Generator[AgentOpsContext]:
    token = set_context(context)
    try:
        yield context
    finally:
        reset_context(token)
