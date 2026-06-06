"""MCP server 配置加载（V-4 修复：分层配置 + 密钥注入）。

设计：
  - 非密配置：app/mcp_servers/config.json（入库）
  - 密配置：.env 或 OS 环境变量（不入库）
  - 启动时从 config.json 读 server 列表 + env_keys
  - 每个 env_key 从 OS env / .env 读真值，注入到 server 启动 env
  - 用 Pydantic Settings 验证（type-safe）

配置示例（config.json）：
  {
    "servers": [
      {
        "id": "mcp-search",
        "command": "python",
        "args": ["-m", "app.mcp_servers.builtin.search_server"],
        "env_keys": ["TAVILY_API_KEY"],
        "startup_phase": "secondary",
        "restart": "on-failure",
        "max_restarts": 5,
        "timeout": 15
      }
    ]
  }
"""
from __future__ import annotations

import json
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# ── 启动阶段（V-1 修复：core/secondary/lazy 分批）────────────────────────
class StartupPhase(str, Enum):
    """启动阶段 — 控制 server 何时拉起。"""

    CORE = "core"             # 启动时立即拉起（用户高频）
    SECONDARY = "secondary"  # 启动 30s 后拉起（低频）
    LAZY = "lazy"             # 首次 call 时拉起（极低频）


# ── 重启策略 ─────────────────────────────────────────────────────────────
class RestartPolicy(str, Enum):
    ON_FAILURE = "on-failure"
    ALWAYS = "always"
    NEVER = "never"


# ── 单个 server 配置 ─────────────────────────────────────────────────────
class ServerConfig(BaseModel):
    id: str
    command: str
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env_keys: list[str] = Field(default_factory=list)  # 需从 vault/.env 注入的密钥名
    extra_env: dict[str, str] = Field(default_factory=dict)  # 静态 env 注入
    startup_phase: StartupPhase = StartupPhase.LAZY
    restart: RestartPolicy = RestartPolicy.ON_FAILURE
    max_restarts: int = 5
    timeout: int = 30
    capability: str = "read"
    version: str = "1.0.0"

    @field_validator("id")
    @classmethod
    def _id_must_be_safe(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Server id {v!r} must be alphanumeric (with - or _)")
        return v


# ── 顶层配置（从 .env 读 SECRET_KEY 等顶层配置）────────────────────────
class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MCP_",
        extra="ignore",
    )

    log_dir: str = "logs"
    large_result_dir: str = "/tmp/mcp_large_results"
    health_check_interval: float = 10.0
    memory_watchdog_gb: float = 4.0


# ── 配置加载 + 密钥注入 ─────────────────────────────────────────────────
class ConfigLoadError(Exception):
    pass


def load_server_config(path: Path | str = "app/mcp_servers/config.json") -> list[ServerConfig]:
    """从 JSON 加载 server 列表，不解析 env_values（host 启动时再注入）。"""
    p = Path(path)
    if not p.exists():
        raise ConfigLoadError(f"Config file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigLoadError(f"Invalid JSON in {p}: {e}") from e
    try:
        return [ServerConfig.model_validate(srv) for srv in data.get("servers", [])]
    except Exception as e:
        raise ConfigLoadError(f"Invalid config in {p}: {e}") from e


def resolve_env(env_keys: list[str], extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """从 OS env / .env 读密钥，注入 server 启动 env。

    优先级：OS env > .env。缺失密钥则抛 ConfigLoadError。
    """
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for key in env_keys:
        value = os.getenv(key)
        if not value:
            missing.append(key)
        else:
            resolved[key] = value
    if missing:
        raise ConfigLoadError(
            f"Missing env keys (set in .env or export): {', '.join(missing)}"
        )
    if extra_env:
        resolved.update(extra_env)
    return resolved


def get_mcp_settings() -> MCPSettings:
    return MCPSettings()  # type: ignore[call-arg]
