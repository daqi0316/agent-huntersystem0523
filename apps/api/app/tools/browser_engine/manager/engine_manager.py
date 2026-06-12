"""
引擎管理器 — 单例模式 + 平台引擎映射 + 降级策略
"""

from typing import Optional, Dict, List
from dataclasses import dataclass
import structlog

from .. import (
    BaseBrowserEngine, EngineType, EngineStatus,
    PageResult, EngineCapability,
)
from ..engine.invisible_engine import InvisiblePlaywrightEngine
from ..engine.browser_use_engine import BrowserUseEngine
from ..engine.http_engine import HTTPEngine

logger = structlog.get_logger()


# 平台 -> 首选引擎映射
PLATFORM_ENGINE_MAP: Dict[str, EngineType] = {
    # 高反爬平台 → invisible_playwright
    "boss_zhipin": EngineType.INVISIBLE_PLAYWRIGHT,
    "liepin": EngineType.INVISIBLE_PLAYWRIGHT,
    "maimai": EngineType.INVISIBLE_PLAYWRIGHT,
    "linkedin": EngineType.INVISIBLE_PLAYWRIGHT,

    # 低反爬平台 → HTTP 直连
    "github": EngineType.HTTP,
    "zhihu": EngineType.HTTP,
    "juejin": EngineType.HTTP,
    "csdn": EngineType.HTTP,
}


@dataclass
class EngineFallbackChain:
    """引擎降级链"""
    primary: EngineType      # 首选
    fallback: EngineType     # 备用
    last_resort: EngineType  # 最后手段


_DEFAULT_FALLBACK_CHAINS: Dict[EngineType, EngineFallbackChain] = {
    EngineType.INVISIBLE_PLAYWRIGHT: EngineFallbackChain(
        primary=EngineType.INVISIBLE_PLAYWRIGHT,
        fallback=EngineType.BROWSER_USE,
        last_resort=EngineType.HTTP,
    ),
    EngineType.BROWSER_USE: EngineFallbackChain(
        primary=EngineType.BROWSER_USE,
        fallback=EngineType.HTTP,
        last_resort=EngineType.HTTP,
    ),
    EngineType.HTTP: EngineFallbackChain(
        primary=EngineType.HTTP,
        fallback=EngineType.HTTP,
        last_resort=EngineType.HTTP,
    ),
}


class EngineManager:
    """
    浏览器引擎管理器
    单例模式，管理所有引擎实例
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: dict = None):
        if self._initialized:
            return

        self.config = config or {}
        self._engines: Dict[EngineType, BaseBrowserEngine] = {}
        self._fallback_chains: Dict[EngineType, EngineFallbackChain] = {
            k: v for k, v in _DEFAULT_FALLBACK_CHAINS.items()
        }

        self._initialized = True
        logger.info("引擎管理器初始化完成")

    def _get_or_create_engine(self, engine_type: EngineType) -> BaseBrowserEngine:
        """获取或创建引擎实例"""
        if engine_type not in self._engines:
            if engine_type == EngineType.INVISIBLE_PLAYWRIGHT:
                self._engines[engine_type] = InvisiblePlaywrightEngine(
                    self.config.get("invisible_playwright", {})
                )
            elif engine_type == EngineType.BROWSER_USE:
                self._engines[engine_type] = BrowserUseEngine(
                    self.config.get("browser_use", {})
                )
            elif engine_type == EngineType.HTTP:
                self._engines[engine_type] = HTTPEngine(
                    self.config.get("http", {})
                )
            else:
                raise ValueError(f"未知引擎类型: {engine_type}")

        return self._engines[engine_type]

    def get_preferred_engine(self, platform_name: str) -> EngineType:
        """
        获取平台的首选引擎
        未配置的平台默认使用 invisible_playwright
        """
        engine_type = PLATFORM_ENGINE_MAP.get(platform_name)
        if engine_type:
            return engine_type

        # 默认：高反爬平台用 invisible_playwright
        logger.warning(
            f"平台 {platform_name} 未配置引擎映射，默认使用 invisible_playwright"
        )
        return EngineType.INVISIBLE_PLAYWRIGHT

    async def fetch_with_fallback(
        self,
        url: str,
        platform_name: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
        max_retries: int = 2,
    ) -> PageResult:
        """
        带降级策略的页面获取

        流程:
        1. 根据平台选择首选引擎
        2. 首选引擎失败 → 降级到备用引擎
        3. 备用引擎失败 → 最后手段（HTTP）
        4. 全部失败 → 返回错误
        """
        primary_engine_type = self.get_preferred_engine(platform_name)
        fallback_chain = self._fallback_chains.get(
            primary_engine_type,
            _DEFAULT_FALLBACK_CHAINS[primary_engine_type],
        )

        engines_to_try = [
            fallback_chain.primary,
            fallback_chain.fallback,
            fallback_chain.last_resort,
        ]

        # 去重（避免 HTTP -> HTTP 重复）
        engines_to_try = list(dict.fromkeys(engines_to_try))

        last_error = None

        for engine_type in engines_to_try:
            engine = self._get_or_create_engine(engine_type)

            # 检查引擎可用性
            if not engine.is_available:
                logger.warning(
                    f"引擎 {engine_type} 不可用，跳过",
                    platform=platform_name,
                )
                continue

            logger.info(
                f"尝试使用引擎 {engine_type}",
                url=url,
                platform=platform_name,
            )

            # 执行获取
            result = await engine.fetch_page(url, wait_for, timeout)
            result.engine_used = engine_type

            if result.success:
                logger.info(
                    f"引擎 {engine_type} 成功获取页面",
                    url=url,
                    platform=platform_name,
                )
                return result

            # 记录失败，继续降级
            last_error = result.error_message
            logger.warning(
                f"引擎 {engine_type} 失败，准备降级",
                url=url,
                error=last_error,
            )

        # 所有引擎都失败
        logger.error(
            "所有引擎均失败",
            url=url,
            platform=platform_name,
            engines_tried=[e.value for e in engines_to_try],
        )

        return PageResult(
            success=False,
            error_message=f"所有引擎失败。最后错误: {last_error}",
            retry_count=max_retries,
        )

    async def health_check_all(self) -> Dict[EngineType, EngineStatus]:
        """检查所有引擎健康状态"""
        results = {}
        for engine_type, engine in self._engines.items():
            results[engine_type] = await engine.health_check()
        return results

    async def close_all(self):
        """关闭所有引擎"""
        for engine_type, engine in self._engines.items():
            try:
                await engine.close()
                logger.info(f"引擎 {engine_type} 已关闭")
            except Exception as e:
                logger.error(f"关闭引擎 {engine_type} 失败", error=str(e))

        self._engines.clear()

    def reset(self):
        """重置单例（主要用于测试）"""
        self._engines.clear()
        self._initialized = False
        EngineManager._instance = None


__all__ = [
    "EngineManager",
    "EngineFallbackChain",
    "PLATFORM_ENGINE_MAP",
]
