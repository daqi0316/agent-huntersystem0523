from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MCPServerCreate(BaseModel):
    """创建 MCP Server 请求"""
    name: str = Field(..., min_length=1, max_length=255)
    server_url: str = Field(..., min_length=1, max_length=1024)
    protocol: str = Field("streamable-http", pattern="^(streamable-http|sse)$")
    auth_type: str = Field("none", pattern="^(none|bearer|basic)$")
    auth_token: str | None = Field(None, max_length=4096)

    @field_validator("server_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("server_url 必须以 http:// 或 https:// 开头")
        return v


class MCPServerUpdate(BaseModel):
    """更新 MCP Server 请求（所有字段可选）"""
    name: str | None = Field(None, min_length=1, max_length=255)
    server_url: str | None = Field(None, min_length=1, max_length=1024)
    protocol: str | None = Field(None, pattern="^(streamable-http|sse)$")
    auth_type: str | None = Field(None, pattern="^(none|bearer|basic)$")
    auth_token: str | None = Field(None, max_length=4096)
    enabled: bool | None = None


class MCPServerRead(BaseModel):
    """MCP Server 响应"""
    id: str
    name: str
    server_url: str
    protocol: str
    auth_type: str
    enabled: bool
    tools_cache: Any = None
    last_heartbeat: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MCPToolDef(BaseModel):
    """MCP Tool 的简化定义（前端用）"""
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPTestConnectionRequest(BaseModel):
    server_url: str = Field(..., min_length=1, max_length=1024)
    auth_type: str = Field("none", pattern="^(none|bearer|basic)$")
    auth_token: str | None = Field(None, max_length=4096)


class MCPTestConnectionResponse(BaseModel):
    success: bool
    server_name: str = ""
    server_version: str = ""
    tools: list[MCPToolDef] = []
    error: str = ""
