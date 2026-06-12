"""LLM factory: config-driven client selection.

v2 多模型接入架构:
  1. 如果有 DB 配置 → 通过 ModelRouter 查主/备模型
  2. 没有 DB 配置 → 从环境变量构造临时 client（向后兼容）

用法:
    from app.llm import get_llm_client
    client = await get_llm_client()   # 异步获取（可能读 DB）
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.llm.base import LLMClient
from app.llm.cn_providers import (
    CN_PROVIDERS,
    DeepSeekClient,
    QwenClient,
    ZhipuClient,
    get_cn_llm_client,
    list_supported_providers,
)
from app.llm.omlx_client import OMLXClient
from app.llm.vllm_client import VLLMClient

logger = logging.getLogger(__name__)

__all__ = [
    "LLMClient",
    "VLLMClient",
    "OMLXClient",
    "QwenClient",
    "DeepSeekClient",
    "ZhipuClient",
    "CN_PROVIDERS",
    "get_llm_client",
    "get_cn_llm_client",
    "list_supported_providers",
]


# ── DB 模式适配器 ──


class _RouterLLMAdapter(LLMClient):
    """将 ModelRouter 包装为 LLMClient 接口，保持向后兼容。"""

    def __init__(self):
        super().__init__(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
        self._router = None

    async def _get_router(self):
        if self._router is None:
            from app.llm.router import get_model_router
            self._router = get_model_router()
        return self._router

    async def chat(self, messages: list[dict], **kwargs) -> str:
        router = await self._get_router()
        try:
            result = await router.chat(messages, **kwargs)
            return result["content"]
        except Exception as e:
            logger.warning("Router chat failed: %s", e)
            raise_on_error = kwargs.pop("raise_on_error", False)
            if raise_on_error:
                raise
            return "[LLM unavailable]"

    async def embed(self, text: str) -> list[float]:
        router = await self._get_router()
        try:
            results = await router.embed([text])
            return results[0] if results else []
        except Exception:
            logger.warning("Router embed failed, using fallback")
            return []


# ── 工厂 ──

_router_adapter: _RouterLLMAdapter | None = None


async def get_llm_client() -> LLMClient:
    """返回 LLM client。

    优先: DB 有 is_primary 配置 → 用 ModelRouter（支持多模型 + 降级）
    兜底: 环境变量 LLM_PROVIDER → 旧模式（单模型）
    """
    # 检查 DB 是否有主模型配置
    try:
        from app.llm.models.llm_provider import LlmProvider
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(LlmProvider).where(LlmProvider.is_primary == True)
            )
            if result.scalar_one_or_none():
                global _router_adapter
                if _router_adapter is None:
                    _router_adapter = _RouterLLMAdapter()
                return _router_adapter
    except Exception as e:
        logger.debug("DB 查询失败，回退到环境变量模式: %s", e)

    # 兜底：环境变量模式（向后兼容）
    return _get_legacy_client()


def _get_legacy_client() -> LLMClient:
    """旧模式：基于环境变量返回单模型 client。"""
    provider = settings.llm_provider.lower()
    if provider == "vllm":
        return VLLMClient()
    if provider in ("omlx", ""):
        return OMLXClient()
    if provider in CN_PROVIDERS:
        return get_cn_llm_client(provider)
    raise ValueError(
        f"Unknown LLM provider: {provider}. "
        f"Supported: omlx/vllm/{'/'.join(CN_PROVIDERS.keys())}"
    )


def reset_llm_client() -> None:
    """重置 Router adapter（测试用）。"""
    global _router_adapter
    _router_adapter = None
