"""OpenAICompatProvider — 统一 OpenAI-compatible API 调用。

覆盖范围:
  - OpenAI (api.openai.com)
  - DeepSeek (api.deepseek.com)
  - 通义千问 (DashScope)
  - 智谱 GLM (open.bigmodel.cn)
  - 本地 OMLX (localhost:8000)
  - vLLM / Ollama / 任何 OpenAI-compatible API

支持:
  - chat completion（含 function/tool calling）
  - SSE streaming
  - embedding
  - 6 类错误分类
  - 连接池复用（按 base_url）
"""

from __future__ import annotations

import time
from typing import AsyncIterator

from openai import (
    APIError,
    APIResponseValidationError,
    APITimeoutError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from openai import AsyncOpenAI

from app.llm.provider.base import (
    BaseProvider,
    ChatResult,
    ConnectionResult,
    ErrorCategory,
    ProviderError,
)


class OpenAICompatProvider(BaseProvider):
    """统一 OpenAI-compatible API Provider。

    连接池：每个不同的 base_url 缓存一个 AsyncOpenAI 实例。
    错误分类：将 OpenAI SDK 异常映射到 ErrorCategory。
    """

    provider_type = "openai_compat"

    # 连接池缓存: base_url → AsyncOpenAI
    _client_cache: dict[str, AsyncOpenAI] = {}

    def _get_client(self, base_url: str, api_key: str | None) -> AsyncOpenAI:
        """获取或创建 AsyncOpenAI 实例（按 base_url 复用）。"""
        if base_url not in self._client_cache:
            self._client_cache[base_url] = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key or "",
                timeout=60.0,
                max_retries=0,  # 由 Router 层控制重试
            )
        return self._client_cache[base_url]

    def invalidate_client(self, base_url: str) -> None:
        """清除连接池中指定 base_url 的缓存（配置变更时调用）。"""
        self._client_cache.pop(base_url, None)

    @classmethod
    def invalidate_all(cls) -> None:
        """清除所有连接池缓存。"""
        cls._client_cache.clear()

    async def chat(
        self,
        model: str,
        messages: list[dict],
        **kwargs,
    ) -> ChatResult:
        base_url = kwargs.pop("base_url", "")
        api_key = kwargs.pop("api_key", None)
        client = self._get_client(base_url, api_key)

        extra_body = kwargs.pop("extra_body", None)
        stream = kwargs.pop("stream", False)

        try:
            create_kwargs = dict(
                model=model,
                messages=messages,
                stream=stream,
                **kwargs,
            )
            if extra_body:
                create_kwargs["extra_body"] = extra_body

            response = await client.chat.completions.create(**create_kwargs)

            return ChatResult(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage=response.usage.model_dump() if response.usage else None,
                provider=self.provider_type,
            )

        except AuthenticationError as e:
            raise ProviderError(
                category=ErrorCategory.AUTH,
                message=str(e),
                status_code=401,
                provider=self.provider_type,
            )
        except RateLimitError as e:
            raise ProviderError(
                category=ErrorCategory.RATE_LIMIT,
                message=str(e),
                status_code=429,
                provider=self.provider_type,
            )
        except APITimeoutError as e:
            raise ProviderError(
                category=ErrorCategory.TIMEOUT,
                message=str(e),
                status_code=None,
                provider=self.provider_type,
            )
        except (NotFoundError, UnprocessableEntityError) as e:
            # 404 = model not found, 422 = bad request
            cat = ErrorCategory.INVALID_MODEL if e.status_code == 404 else ErrorCategory.UNKNOWN
            raise ProviderError(
                category=cat,
                message=str(e),
                status_code=e.status_code,
                provider=self.provider_type,
            )
        except InternalServerError as e:
            raise ProviderError(
                category=ErrorCategory.SERVER_ERROR,
                message=str(e),
                status_code=e.status_code,
                provider=self.provider_type,
            )
        except APIStatusError as e:
            cat = ErrorCategory.SERVER_ERROR if e.status_code >= 500 else ErrorCategory.UNKNOWN
            raise ProviderError(
                category=cat,
                message=str(e),
                status_code=e.status_code,
                provider=self.provider_type,
            )
        except APIError as e:
            raise ProviderError(
                category=ErrorCategory.UNKNOWN,
                message=str(e),
                provider=self.provider_type,
            )

    async def chat_stream(
        self,
        model: str,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[str]:
        base_url = kwargs.pop("base_url", "")
        api_key = kwargs.pop("api_key", None)
        client = self._get_client(base_url, api_key)

        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def embed(
        self,
        model: str,
        texts: list[str],
    ) -> list[list[float]]:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url=model,  # HACK: embed 时 model 参数被复用为 base_url
                api_key="",
                timeout=30.0,
            )
            resp = await client.embeddings.create(
                model="text-embedding-3-small",  # 通用模型名
                input=texts,
            )
            return [d.embedding for d in resp.data]
        except Exception as e:
            raise ProviderError(
                category=ErrorCategory.UNKNOWN,
                message=f"embedding failed: {e}",
                provider=self.provider_type,
            )

    async def check_connection(
        self,
        model: str,
        api_key: str | None,
        base_url: str,
    ) -> ConnectionResult:
        start = time.monotonic()
        try:
            client = self._get_client(base_url, api_key)
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10,
            )
            latency = int((time.monotonic() - start) * 1000)
            return ConnectionResult(
                success=True,
                latency_ms=latency,
                model=resp.model,
                error=None,
            )
        except AuthenticationError as e:
            return ConnectionResult(
                success=False,
                latency_ms=0,
                model=model,
                error=f"认证失败: API Key 无效（{e}）",
            )
        except Exception as e:
            return ConnectionResult(
                success=False,
                latency_ms=0,
                model=model,
                error=f"连接失败: {e}",
            )
