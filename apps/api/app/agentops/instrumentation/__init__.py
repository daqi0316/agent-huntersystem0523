"""AgentOps 业务埋点层 — 无侵入式业务事件发射。

与 business logic 无环依赖，所有方法 fire-and-forget。
"""
from __future__ import annotations

from .recruitment import RecruitmentEvents

__all__ = ["RecruitmentEvents"]
