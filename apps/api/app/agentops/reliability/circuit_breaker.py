from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_seconds: float = 60.0
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    opened_at: float = 0.0

    def allow_request(self, now: float | None = None) -> bool:
        current = monotonic() if now is None else now
        if self.state != CircuitState.OPEN:
            return True
        if current - self.opened_at >= self.recovery_seconds:
            self.state = CircuitState.HALF_OPEN
            return True
        return False

    def record_success(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at = 0.0

    def record_failure(self, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        self.failure_count += 1
        if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at = current

