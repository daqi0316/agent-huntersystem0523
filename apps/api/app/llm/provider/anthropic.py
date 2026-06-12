"""AnthropicProvider — Claude 系列模型调用。

与 OpenAI-compatible API 的关键差异:
  1. 消息格式: content 是 ContentBlock[] 而非 string
  2. 工具格式: input_schema 而非 parameters
  3. 流式格式: event-based 而非 delta-based
  4. 元数据: usage 字段名不同

所有差异在 Provider 内部消化，上层（Router/agent_service）无感知。
"""

from __future__ import annotations

import time
from typing import Any

from app.llm.provider.base import (
    BaseProvider,
    ChatResult,
    ConnectionResult,
    ErrorCategory,
    ProviderError,
)


class AnthropicProvider(BaseProvider):
    """Anthropic Claude Provider。

    使用 anthropic SDK 调用 Claude models。
    消息/工具格式在 _convert_* 方法中转换。
    """

    provider_type = "anthropic"

    _client_cache: dict[str, Any] = {}

    def _get_client(self, api_key: str):
        """获取或创建 Anthropic 客户端（按 api_key 复用实际是复用连接池）。"""
        from httpx import AsyncClient as AsyncHttpClient
        from anthropic import AsyncAnthropic

        if api_key not in self._client_cache:
            http_client = AsyncHttpClient(timeout=60.0)
            self._client_cache[api_key] = AsyncAnthropic(
                api_key=api_key,
                http_client=http_client,
            )
        return self._client_cache[api_key]

    def invalidate_client(self, api_key: str) -> None:
        self._client_cache.pop(api_key, None)

    @classmethod
    def invalidate_all(cls) -> None:
        cls._client_cache.clear()

    # ── 消息格式转换 ──

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """OpenAI 消息格式 → Claude 消息格式。

        OpenAI:  [{"role": "user", "content": "hello"}]
        Claude:  [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]

        主要处理:
          - content 从 string 转为 ContentBlock[]
          - system 消息从 messages 中提取（Claude 用单独的 system 参数）
          - tool_result / tool_call 保留原始格式
        """
        claude_messages = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                # system 消息由调用方通过 kwargs['system'] 传入
                continue

            if isinstance(content, str):
                claude_messages.append({
                    "role": role,
                    "content": [{"type": "text", "text": content}],
                })
            elif isinstance(content, list):
                # tool_result 等格式保持
                claude_messages.append({"role": role, "content": content})
            else:
                claude_messages.append({"role": role, "content": str(content)})

        return claude_messages

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        """OpenAI tools 格式 → Claude tools 格式。

        OpenAI:  [{"type": "function", "function": {"name": "x", "parameters": {...}}}]
        Claude:  [{"name": "x", "input_schema": {...}}]
        """
        if not tools:
            return None

        claude_tools = []
        for tool in tools:
            fn = tool.get("function", {})
            claude_tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {}),
            })
        return claude_tools

    def _convert_usage(self, usage: Any) -> dict:
        """Anthropic usage → OpenAI-compatible usage 格式。"""
        if usage is None:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return {
            "prompt_tokens": getattr(usage, "input_tokens", 0),
            "completion_tokens": getattr(usage, "output_tokens", 0),
            "total_tokens": getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0),
        }

    # ── Provider 接口 ──

    async def chat(
        self,
        model: str,
        messages: list[dict],
        **kwargs,
    ) -> ChatResult:
        api_key = kwargs.pop("api_key", "")
        base_url = kwargs.pop("base_url", "")

        if not api_key:
            raise ProviderError(
                category=ErrorCategory.AUTH,
                message="Anthropic API Key 未配置",
                provider=self.provider_type,
            )

        client = self._get_client(api_key)

        # 提取 system 消息
        system_prompt = None
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
                break

        # 消息格式转换
        claude_messages = self._convert_messages(messages)
        claude_tools = self._convert_tools(kwargs.pop("tools", None))

        # 提取 max_tokens（Claude 的必填参数）
        max_tokens = kwargs.pop("max_tokens", 4096)
        if max_tokens is None or max_tokens <= 0:
            max_tokens = 4096

        try:
            create_kwargs = dict(
                model=model,
                messages=claude_messages,
                max_tokens=max_tokens,
                **kwargs,
            )
            if system_prompt:
                create_kwargs["system"] = system_prompt
            if claude_tools:
                create_kwargs["tools"] = claude_tools

            resp = await client.messages.create(**create_kwargs)

            # 提取文本内容
            content_text = ""
            for block in resp.content:
                if hasattr(block, "text") and block.text:
                    content_text += block.text
                elif hasattr(block, "type") and block.type == "text":
                    content_text += block.text

            return ChatResult(
                content=content_text,
                model=resp.model,
                usage=self._convert_usage(resp.usage),
                provider=self.provider_type,
            )

        except Exception as e:
            err_msg = str(e).lower()
            status = getattr(e, "status_code", None) or getattr(e, "status", None)

            if "authentication" in err_msg or "invalid" in err_msg and "key" in err_msg:
                raise ProviderError(ErrorCategory.AUTH, str(e), status, self.provider_type)
            elif "rate" in err_msg or "too many" in err_msg or status == 429:
                raise ProviderError(ErrorCategory.RATE_LIMIT, str(e), status, self.provider_type)
            elif "timeout" in err_msg or isinstance(e, TimeoutError):
                raise ProviderError(ErrorCategory.TIMEOUT, str(e), None, self.provider_type)
            elif "model" in err_msg and "not found" in err_msg:
                raise ProviderError(ErrorCategory.INVALID_MODEL, str(e), status, self.provider_type)
            elif status and status >= 500:
                raise ProviderError(ErrorCategory.SERVER_ERROR, str(e), status, self.provider_type)
            else:
                raise ProviderError(ErrorCategory.UNKNOWN, str(e), status, self.provider_type)

    async def check_connection(
        self,
        model: str,
        api_key: str | None,
        base_url: str,
    ) -> ConnectionResult:
        if not api_key:
            return ConnectionResult(success=False, latency_ms=0, model=model, error="API Key 未配置")

        start = time.monotonic()
        try:
            client = self._get_client(api_key)
            resp = await client.messages.create(
                model=model,
                messages=[{"role": "user", "content": [{"type": "text", "text": "Hi"}]}],
                max_tokens=10,
            )
            latency = int((time.monotonic() - start) * 1000)
            return ConnectionResult(
                success=True,
                latency_ms=latency,
                model=resp.model,
                error=None,
            )
        except Exception as e:
            return ConnectionResult(
                success=False,
                latency_ms=0,
                model=model,
                error=f"连接失败: {e}",
            )
