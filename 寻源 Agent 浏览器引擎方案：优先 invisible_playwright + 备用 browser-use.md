### 一、设计原则
┌─────────────────────────────────────────────────────────────┐
│                     引擎选择策略                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  第一优先级：invisible_playwright (Firefox C++ 补丁)        │
│  ├── 高反爬平台：BOSS直聘、猎聘、脉脉、LinkedIn              │
│  ├── reCAPTCHA v3 得分 0.90                                │
│  ├── 内置贝塞尔鼠标、相干指纹、时区跟随                       │
│  └── 无需额外反爬代码                                        │
│                                                             │
│  第二优先级：browser-use (Chromium CDP) — 备用               │
│  ├── invisible_playwright 失败时自动降级                     │
│  ├── 低反爬平台可直接使用                                   │
│  ├── 兼容现有代码，无需重写                                  │
│  └── 作为兜底保障                                           │
│                                                             │
│  第三优先级：HTTP 直连 (无浏览器)                             │
│  ├── GitHub API、知乎、掘金等低反爬平台                      │
│  ├── 最高性能，最低资源消耗                                  │
│  └── 无需任何浏览器引擎                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘

### 二、三层引擎架构
┌─────────────────────────────────────────────────────────────────┐
│                        采集 Agent 调度层                         │
│                   (统一入口，自动选择引擎)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              引擎选择器 (Engine Selector)                │   │
│  │                                                         │   │
│  │  输入: platform_name + task_config                      │   │
│  │       │                                                │   │
│  │       ▼                                                │   │
│  │  ┌─────────────┐    失败    ┌─────────────┐           │   │
│  │  │ 策略匹配器   │ ─────────►│ 降级决策器   │           │   │
│  │  │             │           │             │           │   │
│  │  │ boss_zhipin │ ──► invisible_playwright            │   │
│  │  │ liepin      │ ──► invisible_playwright            │   │
│  │  │ maimai      │ ──► invisible_playwright            │   │
│  │  │ linkedin    │ ──► invisible_playwright            │   │
│  │  │ github      │ ──► HTTP 直连                        │   │
│  │  │ zhihu       │ ──► HTTP 直连                        │   │
│  │  │ juejin      │ ──► HTTP 直连                        │   │
│  │  │ unknown     │ ──► invisible_playwright (默认)      │   │
│  │  └─────────────┘           └─────────────┘           │   │
│  │                                     │                  │   │
│  │                                     ▼                  │   │
│  │                           ┌─────────────┐             │   │
│  │                           │ 备用引擎     │             │   │
│  │                           │ browser-use │             │   │
│  │                           └─────────────┘             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                        引擎实现层                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ invisible_      │  │ browser-use     │  │ HTTP Client     │ │
│  │ playwright      │  │ (Chromium CDP)  │  │ (httpx/aiohttp) │ │
│  │ (Firefox)       │  │                 │  │                 │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

### 三、核心代码：引擎抽象层
# backend/src/mcp/tools/browser_engine/__init__.py
"""
浏览器引擎抽象层
支持 invisible_playwright (优先) + browser-use (备用) + HTTP (直连)
"""

from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class EngineType(str, Enum):
    """引擎类型"""
    INVISIBLE_PLAYWRIGHT = "invisible_playwright"
    BROWSER_USE = "browser_use"
    HTTP = "http"


class EngineStatus(str, Enum):
    """引擎状态"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


@dataclass
class EngineCapability:
    """引擎能力描述"""
    engine_type: EngineType
    anti_crawl_level: int  # 1-5，反爬能力等级
    supports_javascript: bool
    supports_cdp: bool
    supports_stealth: bool
    recaptcha_score: float  # reCAPTCHA v3 预期得分
    startup_time_ms: int  # 启动耗时
    memory_mb: int  # 内存占用


@dataclass
class PageResult:
    """页面采集结果"""
    success: bool
    html: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    screenshot: Optional[bytes] = None  # 调试用
    error_message: Optional[str] = None
    engine_used: Optional[EngineType] = None
    retry_count: int = 0


class BaseBrowserEngine(ABC):
    """浏览器引擎基类"""
    
    def __init__(self, config: dict):
        self.config = config
        self._status = EngineStatus.AVAILABLE
        self._consecutive_failures = 0
        self._failure_threshold = 3  # 连续失败阈值
    
    @property
    @abstractmethod
    def engine_type(self) -> EngineType:
        pass
    
    @property
    @abstractmethod
    def capability(self) -> EngineCapability:
        pass
    
    @abstractmethod
    async def health_check(self) -> EngineStatus:
        """健康检查"""
        pass
    
    @abstractmethod
    async def fetch_page(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> PageResult:
        """
        获取页面内容
        所有引擎统一接口
        """
        pass
    
    @abstractmethod
    async def execute_script(self, script: str) -> any:
        """执行 JavaScript"""
        pass
    
    @abstractmethod
    async def close(self):
        """关闭引擎，释放资源"""
        pass
    
    def record_failure(self):
        """记录失败"""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._status = EngineStatus.UNAVAILABLE
            logger.warning(
                f"引擎 {self.engine_type} 标记为不可用",
                failures=self._consecutive_failures,
            )
    
    def record_success(self):
        """记录成功"""
        self._consecutive_failures = 0
        self._status = EngineStatus.AVAILABLE
    
    @property
    def is_available(self) -> bool:
        return self._status != EngineStatus.UNAVAILABLE

### 四、invisible_playwright 引擎实现（优先）
# backend/src/mcp/tools/browser_engine/invisible_engine.py
"""
invisible_playwright 引擎实现 — 第一优先级
高反爬平台主力引擎
"""

from . import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
from invisible_playwright import InvisiblePlaywright
from scrapling import Fetcher
import structlog

logger = structlog.get_logger()


class InvisiblePlaywrightEngine(BaseBrowserEngine):
    """
    invisible_playwright 引擎
    • reCAPTCHA v3: 0.90
    • 反爬等级: 5/5
    • 适用: BOSS直聘、猎聘、脉脉、LinkedIn
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self._playwright: Optional[InvisiblePlaywright] = None
        self._browser = None
        self._page = None
        self._seed = config.get("seed")
        self._proxy = config.get("proxy")
    
    @property
    def engine_type(self) -> EngineType:
        return EngineType.INVISIBLE_PLAYWRIGHT
    
    @property
    def capability(self) -> EngineCapability:
        return EngineCapability(
            engine_type=self.engine_type,
            anti_crawl_level=5,
            supports_javascript=True,
            supports_cdp=False,  # Firefox 无 CDP
            supports_stealth=True,
            recaptcha_score=0.90,
            startup_time_ms=3000,
            memory_mb=400,
        )
    
    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            logger.info("启动 invisible_playwright 引擎")
            
            self._playwright = InvisiblePlaywright(
                proxy=self._proxy,
                seed=self._seed,
                pin=self.config.get("pin", {}),
            )
            self._browser = self._playwright.__enter__()
            logger.info("invisible_playwright 引擎启动完成")
    
    async def health_check(self) -> EngineStatus:
        """健康检查"""
        try:
            await self._ensure_browser()
            page = self._browser.new_page()
            page.goto("https://www.google.com", timeout=10000)
            title = page.title()
            page.close()
            
            if "Google" in title:
                self.record_success()
                return EngineStatus.AVAILABLE
            return EngineStatus.DEGRADED
            
        except Exception as e:
            logger.error("invisible_playwright 健康检查失败", error=str(e))
            self.record_failure()
            return EngineStatus.UNAVAILABLE
    
    async def fetch_page(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> PageResult:
        """
        获取页面
        自动处理：贝塞尔鼠标、相干指纹、时区同步
        """
        try:
            await self._ensure_browser()
            
            # 新建页面（每个 URL 独立页面，隔离状态）
            page = self._browser.new_page()
            
            # 导航到目标 URL
            logger.info("invisible_playwright 开始导航", url=url)
            page.goto(url, wait_until="networkidle", timeout=timeout)
            
            # 等待特定元素（如有）
            if wait_for:
                page.wait_for_selector(wait_for, timeout=timeout)
            
            # 获取结果
            html = page.content()
            title = page.title()
            current_url = page.url
            
            page.close()
            self.record_success()
            
            return PageResult(
                success=True,
                html=html,
                url=current_url,
                title=title,
                engine_used=self.engine_type,
            )
            
        except Exception as e:
            logger.error("invisible_playwright 获取页面失败", url=url, error=str(e))
            self.record_failure()
            return PageResult(
                success=False,
                error_message=str(e),
                engine_used=self.engine_type,
            )
    
    async def execute_script(self, script: str) -> any:
        """执行 JavaScript"""
        if self._page:
            return self._page.evaluate(script)
        raise RuntimeError("无活动页面")
    
    async def close(self):
        """关闭引擎"""
        if self._playwright:
            self._playwright.__exit__(None, None, None)
            self._browser = None
            self._playwright = None
            logger.info("invisible_playwright 引擎已关闭")

### 五、browser-use 引擎实现（备用）
# backend/src/mcp/tools/browser_engine/browser_use_engine.py
"""
browser-use 引擎实现 — 第二优先级（备用）
invisible_playwright 失败时自动降级使用
"""

from . import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
from browser_use import Browser
import structlog

logger = structlog.get_logger()


class BrowserUseEngine(BaseBrowserEngine):
    """
    browser-use 引擎 — 备用方案
    • 反爬等级: 3/5
    • 适用: 低反爬平台，或 invisible_playwright 失败时兜底
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self._browser: Optional[Browser] = None
        self._cdp_url = config.get("cdp_url", "http://localhost:9222")
        self._headless = config.get("headless", False)
    
    @property
    def engine_type(self) -> EngineType:
        return EngineType.BROWSER_USE
    
    @property
    def capability(self) -> EngineCapability:
        return EngineCapability(
            engine_type=self.engine_type,
            anti_crawl_level=3,
            supports_javascript=True,
            supports_cdp=True,
            supports_stealth=False,  # JS 层覆盖，可被检测
            recaptcha_score=0.30,
            startup_time_ms=2000,
            memory_mb=350,
        )
    
    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            logger.info("启动 browser-use 引擎（备用）")
            self._browser = Browser(
                headless=self._headless,
                cdp_url=self._cdp_url,
            )
    
    async def health_check(self) -> EngineStatus:
        """健康检查"""
        try:
            await self._ensure_browser()
            # browser-use 无直接健康检查，尝试获取页面
            return EngineStatus.AVAILABLE
        except Exception as e:
            logger.error("browser-use 健康检查失败", error=str(e))
            return EngineStatus.UNAVAILABLE
    
    async def fetch_page(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> PageResult:
        """获取页面"""
        try:
            await self._ensure_browser()
            
            # browser-use 通过 Agent 操作
            from browser_use import Agent
            
            agent = Agent(
                task=f"打开 {url} 并获取页面内容",
                llm=None,  # 不需要 LLM，纯浏览器操作
                browser=self._browser,
            )
            
            # 执行导航
            await agent.run()
            
            # 获取页面内容（通过 CDP）
            html = await self._browser.get_page_source()
            
            self.record_success()
            
            return PageResult(
                success=True,
                html=html,
                url=url,
                engine_used=self.engine_type,
            )
            
        except Exception as e:
            logger.error("browser-use 获取页面失败", url=url, error=str(e))
            self.record_failure()
            return PageResult(
                success=False,
                error_message=str(e),
                engine_used=self.engine_type,
            )
    
    async def execute_script(self, script: str) -> any:
        """执行 JavaScript"""
        if self._browser:
            return await self._browser.execute_script(script)
        raise RuntimeError("浏览器未启动")
    
    async def close(self):
        """关闭引擎"""
        if self._browser:
            await self._browser.close()
            self._browser = None
            logger.info("browser-use 引擎已关闭")

### 六、HTTP 直连引擎（第三优先级）
# backend/src/mcp/tools/browser_engine/http_engine.py
"""
HTTP 直连引擎 — 第三优先级
适用于无反爬或低反爬平台（GitHub API、知乎、掘金等）
"""

from . import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
import httpx
import structlog

logger = structlog.get_logger()


class HTTPEngine(BaseBrowserEngine):
    """
    HTTP 直连引擎
    • 反爬等级: 1/5
    • 最高性能，最低资源消耗
    • 适用: GitHub API、知乎、掘金、CSDN
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/125.0.0.0 Safari/537.36",
            },
        )
    
    @property
    def engine_type(self) -> EngineType:
        return EngineType.HTTP
    
    @property
    def capability(self) -> EngineCapability:
        return EngineCapability(
            engine_type=self.engine_type,
            anti_crawl_level=1,
            supports_javascript=False,  # 无 JS 执行能力
            supports_cdp=False,
            supports_stealth=False,
            recaptcha_score=0.0,  # 无法过 reCAPTCHA
            startup_time_ms=0,  # 无启动耗时
            memory_mb=10,
        )
    
    async def health_check(self) -> EngineStatus:
        """HTTP 引擎始终可用"""
        return EngineStatus.AVAILABLE
    
    async def fetch_page(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> PageResult:
        """HTTP GET 请求"""
        try:
            response = await self._client.get(url, timeout=timeout / 1000)
            response.raise_for_status()
            
            return PageResult(
                success=True,
                html=response.text,
                url=str(response.url),
                engine_used=self.engine_type,
            )
            
        except Exception as e:
            logger.error("HTTP 请求失败", url=url, error=str(e))
            return PageResult(
                success=False,
                error_message=str(e),
                engine_used=self.engine_type,
            )
    
    async def execute_script(self, script: str) -> any:
        """HTTP 引擎不支持 JS 执行"""
        raise NotImplementedError("HTTP 引擎不支持 JavaScript 执行")
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self._client.aclose()
        logger.info("HTTP 引擎已关闭")

### 七、引擎调度器（核心）
# backend/src/mcp/tools/browser_engine/engine_manager.py
"""
浏览器引擎管理器
自动选择最优引擎，支持降级策略
"""

from typing import Optional, Dict, List
from dataclasses import dataclass
import structlog

from . import (
    BaseBrowserEngine, EngineType, EngineStatus, 
    PageResult, EngineCapability,
)
from .invisible_engine import InvisiblePlaywrightEngine
from .browser_use_engine import BrowserUseEngine
from .http_engine import HTTPEngine

logger = structlog.get_logger()


# 平台 -> 首选引擎映射
PLATFORM_ENGINE_MAP = {
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
        fallback_chain = self._fallback_chains[primary_engine_type]
        
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
            f"所有引擎均失败",
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

### 八、平台适配器重写（使用引擎管理器）
# backend/src/mcp/adapters/boss_zhipin_v3.py
"""
BOSS直聘适配器 v3 — 使用引擎管理器
自动选择 invisible_playwright (优先) → browser-use (备用)
"""

from .base import PlatformAdapter, CrawlResult, PlatformStatus
from ..tools.browser_engine.engine_manager import EngineManager
from scrapling import Fetcher
import structlog

logger = structlog.get_logger()


class BossZhipinAdapterV3(PlatformAdapter):
    """
    BOSS直聘适配器 v3
    引擎策略: invisible_playwright (优先) → browser-use (备用) → HTTP (最后)
    """
    
    name = "boss_zhipin"
    display_name = "BOSS直聘"
    category = "job_board"
    anti_crawl_level = 5
    requires_login = True
    supports_realtime = True
    
    BASE_URL = "https://www.zhipin.com"
    
    def __init__(self, config: dict, proxy_pool, fingerprint_manager):
        super().__init__(config, proxy_pool, fingerprint_manager)
        self._engine_manager = EngineManager(config.get("engine_manager", {}))
    
    async def health_check(self) -> PlatformStatus:
        """健康检查"""
        health = await self._engine_manager.health_check_all()
        
        # 只要 invisible_playwright 或 browser-use 可用即可
        if health.get("invisible_playwright") == EngineStatus.AVAILABLE:
            return PlatformStatus.HEALTHY
        if health.get("browser_use") == EngineStatus.AVAILABLE:
            return PlatformStatus.DEGRADED
        
        return PlatformStatus.DOWN
    
    async def search(self, keyword: str, filters: dict = None) -> CrawlResult:
        """
        执行搜索
        引擎管理器自动处理降级逻辑
        """
        filters = filters or {}
        search_url = self._build_search_url(keyword, filters)
        
        # 使用引擎管理器获取页面（自动降级）
        result = await self._engine_manager.fetch_with_fallback(
            url=search_url,
            platform_name=self.name,
            wait_for=".job-card-wrapper",
            timeout=30000,
        )
        
        if not result.success:
            return CrawlResult(
                success=False,
                error_message=result.error_message,
            )
        
        # 解析候选人列表
        candidates = await self.parse_list_page(result.html)
        
        return CrawlResult(
            success=True,
            candidates=candidates[:20],
            raw_html=result.html[:50000],
            engine_used=result.engine_used.value if result.engine_used else None,
        )
    
    async def parse_list_page(self, html: str) -> list[dict]:
        """解析列表页 — 与之前相同"""
        fetcher = Fetcher()
        page = fetcher.get(html)
        
        candidates = []
        items = page.css(".job-card-wrapper")
        
        for item in items:
            try:
                candidate = {
                    "name": item.css(".name").text(),
                    "title": item.css(".job-title").text(),
                    "company": item.css(".company-name").text(),
                    "location": item.css(".job-area").text(),
                    "salary": item.css(".salary").text(),
                    "experience": item.css(".tag-list .tag").text(),
                    "detail_url": item.css("a").attr("href"),
                    "source_platform": self.name,
                }
                candidates.append(candidate)
            except Exception:
                continue
        
        return candidates
    
    async def get_detail(self, candidate_url: str) -> CrawlResult:
        """获取详情页"""
        result = await self._engine_manager.fetch_with_fallback(
            url=candidate_url,
            platform_name=self.name,
            timeout=30000,
        )
        
        if not result.success:
            return CrawlResult(success=False, error_message=result.error_message)
        
        # 解析详情
        candidate = await self.parse_detail_page(result.html)
        candidate["detail_url"] = candidate_url
        
        return CrawlResult(
            success=True,
            candidates=[candidate],
            engine_used=result.engine_used.value if result.engine_used else None,
        )
    
    async def parse_detail_page(self, html: str) -> dict:
        """解析详情页"""
        # 实现详情页解析
        pass
    
    def _build_search_url(self, keyword: str, filters: dict) -> str:
        """构建搜索 URL"""
        import urllib.parse
        query = urllib.parse.quote(keyword)
        url = f"{self.BASE_URL}/web/geek/job?query={query}"
        
        if city := filters.get("location"):
            url += f"&city={city}"
        if exp := filters.get("experience_years"):
            url += f"&experience={exp}"
        
        return url
    
    async def cleanup(self):
        """清理资源"""
        await self._engine_manager.close_all()

### 九、配置更新
# backend/src/config.py — 引擎管理配置

class Settings(BaseSettings):
    # ... 原有配置 ...
    
    # ============ 引擎管理器配置 ============
    ENGINE_MANAGER = {
        # invisible_playwright 配置
        "invisible_playwright": {
            "cache_dir": "~/.cache/invisible_playwright",
            "default_seed": None,  # None = 随机种子
            "default_pin": {
                "screen.width": 1920,
                "screen.height": 1080,
            },
        },
        
        # browser-use 备用配置
        "browser_use": {
            "cdp_url": "http://localhost:9222",
            "headless": False,
        },
        
        # HTTP 直连配置
        "http": {
            "timeout": 30.0,
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
        },
    }
    
    # 平台引擎映射（可自定义覆盖）
    PLATFORM_ENGINE_MAP = {
        "boss_zhipin": "invisible_playwright",
        "liepin": "invisible_playwright",
        "maimai": "invisible_playwright",
        "linkedin": "invisible_playwright",
        "github": "http",
        "zhihu": "http",
        "juejin": "http",
    }

### 十、降级策略可视化
┌─────────────────────────────────────────────────────────────────┐
│                    页面获取流程（带降级）                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户请求: 采集 BOSS直聘候选人                                   │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────┐                                            │
│  │ 引擎管理器       │                                            │
│  │                 │                                            │
│  │ 1. 查映射表:    │──► boss_zhipin → invisible_playwright     │
│  │                 │                                            │
│  │ 2. 检查健康:    │──► invisible_playwright 可用?              │
│  │    ✅ 可用      │                                            │
│  │       │         │                                            │
│  │       ▼         │                                            │
│  │ 3. 执行获取      │──► invisible_playwright.fetch_page()      │
│  │       │         │                                            │
│  │       ▼         │                                            │
│  │ 4. 成功?        │                                            │
│  │    ✅ 成功 ─────┼──► 返回结果，记录引擎类型                   │
│  │    ❌ 失败      │                                            │
│  │       │         │                                            │
│  │       ▼         │                                            │
│  │ 5. 降级到备用   │──► browser_use.fetch_page()                │
│  │       │         │                                            │
│  │       ▼         │                                            │
│  │ 6. 成功?        │                                            │
│  │    ✅ 成功 ─────┼──► 返回结果，记录降级事件                   │
│  │    ❌ 失败      │                                            │
│  │       │         │                                            │
│  │       ▼         │                                            │
│  │ 7. 最后手段      │──► HTTP 请求（可能无 JS 内容）             │
│  │       │         │                                            │
│  │       ▼         │                                            │
│  │ 8. 全部失败      │──► 返回错误，记录日志，告警                 │
│  │                 │                                            │
│  └─────────────────┘                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

### 十一、监控与告警
# backend/src/services/tasks/crawl_task_v2.py
"""
带引擎降级监控的采集任务
"""

from celery import shared_task
import structlog

logger = structlog.get_logger()


@shared_task(bind=True, max_retries=3)
def crawl_platform_task_v2(self, platform_name: str, keyword: str, task_id: str):
    """增强版采集任务 — 记录引擎降级事件"""
    
    from src.mcp.tools.browser_engine.engine_manager import EngineManager
    
    engine_manager = EngineManager()
    
    # 执行采集（自动降级）
    result = await engine_manager.fetch_with_fallback(
        url=search_url,
        platform_name=platform_name,
    )
    
    # 记录引擎使用情况
    logger.info(
        "采集任务完成",
        task_id=task_id,
        platform=platform_name,
        engine_used=result.engine_used,
        success=result.success,
    )
    
    # 如果发生降级，发送告警
    preferred_engine = engine_manager.get_preferred_engine(platform_name)
    if result.engine_used != preferred_engine.value:
        logger.warning(
            "引擎降级发生",
            task_id=task_id,
            platform=platform_name,
            preferred=preferred_engine.value,
            actual=result.engine_used,
            url=url,
        )
        # TODO: 发送钉钉/企业微信告警
    
    return {
        "platform": platform_name,
        "engine_used": result.engine_used,
        "success": result.success,
        "html_length": len(result.html) if result.html else 0,
    }

### 十二、实施路线图（更新）
| 阶段          | 任务                                | 时间    | 说明                                                |
| ----------- | --------------------------------- | ----- | ------------------------------------------------- |
| **Phase 0** | 安装 invisible\_playwright，验证 macOS | 30 分钟 | `pip install` + `fetch` + 清除隔离属性                  |
| **Phase 1** | 实现引擎抽象层 + 三个引擎                    | 1 天   | BaseBrowserEngine + Invisible + BrowserUse + HTTP |
| **Phase 2** | 实现引擎管理器 + 降级逻辑                    | 半天    | EngineManager + fallback 策略                       |
| **Phase 3** | 重写 BOSS直聘适配器（v3）                  | 半天    | 使用引擎管理器                                           |
| **Phase 4** | 对比测试                              | 半天    | invisible vs browser-use vs HTTP                  |
| **Phase 5** | 重写猎聘/脉脉适配器                        | 1 天   | 复用引擎管理器                                           |
| **Phase 6** | 删除冗余反爬代码                          | 半天    | 删除 mouse\_simulator 等                             |
| **Phase 7** | 监控告警 + 文档                         | 半天    | 降级事件告警                                            |
