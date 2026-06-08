"""ToolRegistry — 工具注册表 = 单一事实源（v4 V-4 schema 演进 + 启动 dump）。

设计目标：
  - 启动时从所有 server list_tools() 收集 → 集中索引
  - 支持 version 字段（多版本共存）
  - 支持 deprecation（v1 → v2 迁移期并存）
  - 支持 capability 字段（read/write/destructive/admin）
  - 冲突检测（同名同 server_id 重复注册 → 报错）
  - 持久化 snapshot 到 JSON（CI 比对 / 文档生成）
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ToolEntry:
    """单个 tool 的注册项。"""

    name: str                       # 工具名（OpenAI 短名，例 'calculate'）
    server_id: str                  # 提供此 tool 的 server
    capability: str = "read"        # read | write | destructive | admin
    version: str = "1.0.0"
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    deprecated: bool = False
    deprecated_since: Optional[str] = None
    replacement: Optional[str] = None  # 指向新工具名


class ToolRegistry:
    """工具注册表（线程/协程安全 — 但不锁，靠 supervisor 串行 register）。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    # ── 写入 ─────────────────────────────────────────────────────
    def register(
        self,
        name: str,
        server_id: str,
        *,
        capability: str = "read",
        version: str = "1.0.0",
        description: str = "",
        input_schema: dict | None = None,
    ) -> None:
        """注册一个 tool。

        冲突检测：同名同 server 重复 → 覆盖（同 server 重启时调用）。
        跨 server 同名 → 拒绝（防止远程 MCP 和内置重名）。
        """
        if name in self._tools:
            existing = self._tools[name]
            if existing.server_id != server_id:
                raise ValueError(
                    f"Tool name conflict: {name!r} registered on "
                    f"{existing.server_id!r} and {server_id!r}"
                )
            logger.debug("Re-registering tool %s on %s (server restart)", name, server_id)
        self._tools[name] = ToolEntry(
            name=name,
            server_id=server_id,
            capability=capability,
            version=version,
            description=description,
            input_schema=input_schema or {},
        )

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def unregister_by_server(self, server_id: str) -> list[str]:
        """server 挂了 / 重启前清空它的所有 tool，返回被清空的 name 列表。"""
        removed = [n for n, e in self._tools.items() if e.server_id == server_id]
        for n in removed:
            del self._tools[n]
        return removed

    # ── 读取 ─────────────────────────────────────────────────────
    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def all(self) -> list[ToolEntry]:
        return list(self._tools.values())

    def by_server(self, server_id: str) -> list[ToolEntry]:
        return [e for e in self._tools.values() if e.server_id == server_id]

    def by_capability(self, capability: str) -> list[ToolEntry]:
        return [e for e in self._tools.values() if e.capability == capability]

    def tool_count(self) -> int:
        return len(self._tools)

    def server_count(self) -> int:
        return len({e.server_id for e in self._tools.values()})

    # ── schema 演进（v4 V-4）────────────────────────────────────
    def deprecate(
        self, name: str, replacement: str | None = None
    ) -> None:
        """标 deprecated。LLM 仍可调但 metadata 会标。"""
        entry = self._tools.get(name)
        if not entry:
            raise KeyError(f"Unknown tool: {name}")
        entry.deprecated = True
        entry.deprecated_since = datetime.now(timezone.utc).isoformat()
        entry.replacement = replacement

    def is_deprecated(self, name: str) -> bool:
        entry = self._tools.get(name)
        return entry.deprecated if entry else False

    # ── 序列化（CI 校验 / 文档生成）─────────────────────────────
    def dump_snapshot(self, path: Path | str) -> None:
        """把当前注册表 dump 到 JSON，用于 CI 比对 + docs 生成。"""
        p = Path(path)
        snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool_count": self.tool_count(),
            "server_count": self.server_count(),
            "tools": [
                {
                    **{k: v for k, v in asdict(e).items() if v is not None or k in ("description", "input_schema")},
                    "name": e.name,
                    "server_id": e.server_id,
                }
                for e in sorted(self._tools.values(), key=lambda x: (x.server_id, x.name))
            ],
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Registry snapshot dumped: %d tools → %s", self.tool_count(), p)

    def get_all_schemas(self, format: str = "mcp") -> list[dict]:
        """返回所有 tool schemas（mcp 格式 / openai 格式）。"""
        if format == "openai":
            return [
                {
                    "type": "function",
                    "function": {
                        "name": e.name,
                        "description": e.description,
                        "parameters": e.input_schema,
                    },
                }
                for e in self._tools.values()
            ]
        return [
            {
                "name": e.name,
                "description": e.description,
                "inputSchema": e.input_schema,
                "meta": {
                    "capability": e.capability,
                    "version": e.version,
                    "server": e.server_id,
                    "deprecated": e.deprecated,
                    "replacement": e.replacement,
                },
            }
            for e in self._tools.values()
        ]
