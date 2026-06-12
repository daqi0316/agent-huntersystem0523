"""ModelRouter — 模型路由：主模型 → 失败降级 → 返回。

不做复杂路由。只做:
  1. 查 is_primary → 调 → 成功？返回
  2. 失败（可降级类错误）→ 查 is_fallback → 调 → 成功？返回
  3. 全失败 → 报错
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.llm.provider.base import ChatResult, ProviderError
from app.llm.provider.pool import get_provider_pool
from app.llm.router.cache import ProviderConfigCache

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AllProvidersFailed(Exception):
    """所有模型都失败时抛出。"""
    def __init__(self, errors: list[tuple[str, ProviderError]]):
        self.errors = errors
        detail = "; ".join(f"{name}: {err}" for name, err in errors)
        super().__init__(f"所有模型调用失败: {detail}")


class EmbeddingNotAvailable(Exception):
    """没有可用的 embedding 模型。"""


class ModelRouter:
    """模型路由器 — 主→备→报错。"""

    def __init__(self):
        self._cache = ProviderConfigCache()
        self._pool = get_provider_pool()

    # ── 公开接口 ──

    async def chat(
        self,
        messages: list[dict],
        **kwargs,
    ) -> ChatResult:
        """调用主模型，失败时降级到备用。

        参数:
            messages: OpenAI 格式的消息列表
            **kwargs: 透传给 Provider.chat() 的参数

        返回:
            ChatResult

        异常:
            AllProvidersFailed: 所有模型均失败
        """
        primary, fallback = await self._cache.get()
        errors: list[tuple[str, ProviderError]] = []

        # 尝试主模型
        if primary:
            try:
                return await self._call_provider(primary, messages, kwargs)
            except ProviderError as e:
                errors.append(("primary", e))
                if not e.should_fallback():
                    # 401 等错误不降级，直接抛
                    raise AllProvidersFailed(errors) from e
                logger.warning("主模型 %s 失败，准备降级: %s", primary.name, e)

        # 降级到备用
        if fallback:
            try:
                return await self._call_provider(fallback, messages, kwargs)
            except ProviderError as e:
                errors.append(("fallback", e))
                logger.warning("备用模型 %s 也失败: %s", fallback.name, e)

        raise AllProvidersFailed(errors)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化。

        优先用主模型，不支持则找备用或其他支持 embedding 的模型。
        """
        primary, fallback = await self._cache.get()

        # 优先主模型
        for cfg in [primary, fallback]:
            if cfg and cfg.capabilities.get("embedding", False):
                try:
                    provider = await self._pool.get_provider(cfg.provider_type)
                    return await provider.embed(cfg.model_name, texts)
                except (NotImplementedError, ProviderError):
                    continue

        # 兜底：查 DB 找支持 embedding 的模型
        embed_cfg = await self._find_embed_model()
        if embed_cfg:
            provider = await self._pool.get_provider(embed_cfg.provider_type)
            try:
                return await provider.embed(embed_cfg.model_name, texts)
            except (NotImplementedError, ProviderError) as e:
                logger.warning("embed 降级模型也失败: %s", e)

        raise EmbeddingNotAvailable("没有可用的 embedding 模型")

    async def check_connection(
        self,
        provider_type: str,
        model_name: str,
        api_key: str | None,
        base_url: str,
    ) -> dict:
        """测试指定配置的连通性（管理 API 调用）。"""
        try:
            provider = await self._pool.get_provider(provider_type)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        result = await provider.check_connection(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
        )
        return dict(result)

    def invalidate_cache(self) -> None:
        """主动失效配置缓存。"""
        self._cache.invalidate()

    # ── 内部 ──

    async def _call_provider(
        self,
        cfg,
        messages: list[dict],
        kwargs: dict,
    ) -> ChatResult:
        """调用单个 Provider。"""
        provider = await self._pool.get_provider(cfg.provider_type)

        # 注入连接参数
        call_kwargs = {
            **kwargs,
            "base_url": cfg.base_url,
            "api_key": cfg.api_key,
        }

        return await provider.chat(
            model=cfg.model_name,
            messages=messages,
            **call_kwargs,
        )

    async def _find_embed_model(self):
        """查 DB 找支持 embedding 的第一个 active 模型。"""
        try:
            from app.llm.models.llm_provider import LlmProvider
            from sqlalchemy import select
            from app.llm.admin.crypto import decrypt_api_key
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(LlmProvider).where(
                        LlmProvider.is_active == True,
                        LlmProvider.capabilities["embedding"].astext.cast(
                            __import__("sqlalchemy").Boolean
                        ) == True,
                    ).order_by(LlmProvider.sort_order).limit(1)
                )
                row = result.scalar_one_or_none()
                if row:
                    from app.llm.router.cache import ProviderConfig
                    return ProviderConfig(
                        id=row.id,
                        name=row.name,
                        provider_type=row.provider_type,
                        base_url=row.base_url,
                        model_name=row.model_name,
                        api_key=decrypt_api_key(row.api_key_enc) if row.api_key_enc else None,
                        timeout_seconds=row.timeout_seconds,
                        max_retries=row.max_retries,
                        capabilities=row.capabilities or {},
                        is_primary=False,
                        is_fallback=False,
                        is_active=True,
                    )
        except Exception as e:
            logger.warning("查找 embedding 模型失败: %s", e)
        return None


# ── 全局单例 ──

_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """获取全局 ModelRouter 单例。"""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def reset_model_router() -> None:
    """重置单例（测试用）。"""
    global _router
    _router = None
