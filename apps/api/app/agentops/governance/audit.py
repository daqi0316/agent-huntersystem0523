"""治理配置变更审计日志 (P2-C Stage 13).

记录所有治理配置的变更，支持回溯和责任追查。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class AuditEntry:
    """单条审计记录。

    Attributes:
        timestamp: 变更时间。
        actor: 操作人 (user_id / system / scheduler)。
        action: 操作类型 (create/update/delete/validate/apply)。
        resource: 资源类型 (sampling/governance/privacy/evaluation)。
        resource_id: 资源标识 (配置名称 / tenant_id 等)。
        detail: 变更详情 (JSON string)。
        previous: 变更前的值 (可选)。
        current: 变更后的值 (可选)。
        source_ip: 来源 IP (可选)。
    """

    timestamp: datetime
    actor: str
    action: str
    resource: str
    resource_id: str
    detail: str = ""
    previous: str | None = None
    current: str | None = None
    source_ip: str = ""


class AuditLog:
    """审计日志存储（默认 in-memory，可扩展为 DB）。"""

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries

    def record(
        self,
        actor: str,
        action: str,
        resource: str,
        resource_id: str,
        *,
        detail: str = "",
        previous: str | None = None,
        current: str | None = None,
        source_ip: str = "",
    ) -> AuditEntry:
        """记录一条审计日志。"""
        entry = AuditEntry(
            timestamp=datetime.now(UTC),
            actor=actor,
            action=action,
            resource=resource,
            resource_id=resource_id,
            detail=detail,
            previous=previous,
            current=current,
            source_ip=source_ip,
        )
        self._entries.append(entry)
        # 超过上限时裁剪旧记录
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        return entry

    def query(
        self,
        *,
        actor: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        resource_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """查询审计日志，支持过滤。"""
        results = list(self._entries)
        if actor:
            results = [e for e in results if e.actor == actor]
        if action:
            results = [e for e in results if e.action == action]
        if resource:
            results = [e for e in results if e.resource == resource]
        if resource_id:
            results = [e for e in results if e.resource_id == resource_id]
        return results[offset:offset + limit]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def export_csv(self) -> str:
        """导出为 CSV 格式。"""
        lines = ["timestamp,actor,action,resource,resource_id,detail"]
        for e in self._entries:
            ts = e.timestamp.isoformat()
            detail_escaped = e.detail.replace('"', '""')
            lines.append(f"{ts},{e.actor},{e.action},{e.resource},{e.resource_id},\"{detail_escaped}\"")
        return "\n".join(lines)
