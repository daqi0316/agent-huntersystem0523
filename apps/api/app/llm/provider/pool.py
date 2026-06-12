"""ProviderPool — 模型提供者连接池管理。

职责:
  1. 按 provider_type 缓存 Provider 实例（懒加载）
  2. 提供统一的 get_provider() 入口
  3. 配置变更时 invalidate 连接缓存
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.llm.provider.base import BaseProvider

logger = logging.getLogger(__name__)


class ProviderPool:
    """Provider 实例池。

    线程安全: 用 asyncio.Lock 保护懒加载。
    """

    def __init__(self):
        self._providers: dict[str, "BaseProvider"] = {}
        self._lock = None

    @property
    def lock(self):
        if self._lock is None:
            import asyncio
            self._lock = asyncio.Lock()
        return self._lock

    async def get_provider(self, provider_type: str) -> "BaseProvider":
        """获取指定类型的 Provider 实例（懒加载 + 缓存）。

        参数:
            provider_type: "openai_compat" | "anthropic"

        返回:
            BaseProvider 实例

        异常:
            ValueError: 不支持的 provider_type
        """
        if provider_type not in self._providers:
            async with self.lock:
                # 双重检查
                if provider_type not in self._providers:
                    self._providers[provider_type] = self._create(provider_type)
                    logger.info("ProviderPool: 创建 %s 实例", provider_type)
        return self._providers[provider_type]

    async def has_provider(self, provider_type: str) -> bool:
        """检查是否支持该 provider 类型。"""
        try:
            await self.get_provider(provider_type)
            return True
        except ValueError:
            return False

    def invalidate(self, provider_type: str) -> None:
        """清除指定类型的 Provider 实例（配置变更时调用）。"""
        provider = self._providers.pop(provider_type, None)
        if provider:
            # 清除该 Provider 内部的连接池
            if hasattr(provider, "invalidate_all"):
                provider.invalidate_all()
            logger.info("ProviderPool: 清除 %s 实例缓存", provider_type)

    def invalidate_all(self) -> None:
        """清除所有 Provider 实例。"""
        for provider_type in list(self._providers.keys()):
            self.invalidate(provider_type)
        self._providers.clear()
        logger.info("ProviderPool: 清除所有 Provider 缓存")

    @staticmethod
    def _create(provider_type: str) -> "BaseProvider":
        """工厂方法 — 创建 Provider 实例。"""
        if provider_type == "openai_compat":
            from app.llm.provider.openai_compat import OpenAICompatProvider
            return OpenAICompatProvider()
        elif provider_type == "anthropic":
            from app.llm.provider.anthropic import AnthropicProvider
            return AnthropicProvider()
        else:
            raise ValueError(
                f"不支持的 provider 类型: {provider_type}。"
                f"可用: openai_compat, anthropic"
            )


# ── 全局单例 ──

_provider_pool: ProviderPool | None = None


def get_provider_pool() -> ProviderPool:
    """获取全局 ProviderPool 单例。"""
    global _provider_pool
    if _provider_pool is None:
        _provider_pool = ProviderPool()
    return _provider_pool


def reset_provider_pool() -> None:
    """重置单例（测试用）。"""
    global _provider_pool
    _provider_pool = None
