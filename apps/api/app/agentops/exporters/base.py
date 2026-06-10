from __future__ import annotations

from typing import Protocol

from app.agentops.core.schemas import BaseEvent


class AgentOpsExporter(Protocol):
    async def export(self, event: BaseEvent) -> None: ...

    async def flush(self) -> None: ...

    async def shutdown(self) -> None: ...

