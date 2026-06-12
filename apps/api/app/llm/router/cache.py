"""ProviderConfigCache — 主备模型配置缓存。

减少每次 LLM 调用都查 DB 的压力。
策略：30s TTL + 管理 API 写操作后主动 invalidate。
无 Redis 时退化到进程内 dict 缓存。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """从 DB llm_providers 行映射到的运行时配置。"""
    id: str
    name: str
    provider_type: str       # "openai_compat" | "anthropic"
    base_url: str
    model_name: str
    api_key: str | None      # 解密后的 API Key
    timeout_seconds: int
    max_retries: int
    capabilities: dict
    is_primary: bool
    is_fallback: bool
    is_active: bool


class ProviderConfigCache:
    """主备模型配置缓存。

    TTL 30s，管理 API 写操作后通过 invalidate() 主动失效。
    """

    TTL = 30.0  # 秒

    def __init__(self):
        self._primary: ProviderConfig | None = None
        self._fallback: ProviderConfig | None = None
        self._updated_at: float = 0.0

    async def get(self) -> tuple[ProviderConfig | None, ProviderConfig | None]:
        """获取主模型 + 备用模型配置。

        返回: (primary_config, fallback_config)
        """
        now = time.monotonic()
        if now - self._updated_at < self.TTL:
            return self._primary, self._fallback

        # 缓存过期，从 DB 重新加载
        return await self._reload()

    async def _reload(self) -> tuple[ProviderConfig | None, ProviderConfig | None]:
        """从 DB 加载主备配置。"""
        try:
            from app.llm.admin.crypto import decrypt_api_key
            from app.llm.models.llm_provider import LlmProvider
            from sqlalchemy import or_, select
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(LlmProvider).where(
                        or_(LlmProvider.is_primary == True, LlmProvider.is_fallback == True)
                    )
                )
                rows = result.scalars().all()

                self._primary = None
                self._fallback = None

                for row in rows:
                    cfg = ProviderConfig(
                        id=row.id,
                        name=row.name,
                        provider_type=row.provider_type,
                        base_url=row.base_url,
                        model_name=row.model_name,
                        api_key=decrypt_api_key(row.api_key_enc) if row.api_key_enc else None,
                        timeout_seconds=row.timeout_seconds,
                        max_retries=row.max_retries,
                        capabilities=row.capabilities or {},
                        is_primary=row.is_primary,
                        is_fallback=row.is_fallback,
                        is_active=row.is_active,
                    )
                    if cfg.is_primary and cfg.is_active:
                        self._primary = cfg
                    elif cfg.is_fallback and cfg.is_active:
                        self._fallback = cfg

                self._updated_at = time.monotonic()
                logger.debug(
                    "ProviderConfigCache: 已加载 primary=%s fallback=%s",
                    self._primary.name if self._primary else "None",
                    self._fallback.name if self._fallback else "None",
                )
        except Exception as e:
            logger.error("ProviderConfigCache 加载失败: %s", e)
            # 缓存过期但加载失败，保留旧值
            self._updated_at = time.monotonic()

        return self._primary, self._fallback

    def invalidate(self) -> None:
        """主动失效缓存（管理 API 写操作后调用）。"""
        self._updated_at = 0.0
        logger.info("ProviderConfigCache: 已失效")
