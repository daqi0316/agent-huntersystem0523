# 寻源 Agent 浏览器引擎方案 — 工程化升级规划 v5

> 基于「寻源 Agent 浏览器引擎方案：优先 invisible_playwright + 备用 browser-use.md」完整复刻
> Momus 审核修正：保留全部原文代码 + 工程化增量扩展（不替换原文任何逻辑）
> 项目实际路径：`apps/api/app/tools/browser_engine/`

---

## 目录

1. [设计原则](#一设计原则)
2. [三层引擎架构](#二三层引擎架构)
3. [引擎抽象层](#三引擎抽象层)
4. [InvisiblePlaywright 引擎实现](#四invisible_playwright-引擎实现优先)
5. [BrowserUse 引擎实现](#五browser-use-引擎实现备用)
6. [HTTP 引擎实现](#六http-直连引擎第三优先级)
7. [引擎调度器](#七引擎调度器核心)
8. [平台适配器重写](#八平台适配器重写使用引擎管理器)
9. [配置体系](#九配置更新)
10. [降级策略可视化](#十降级策略可视化)
11. [监控与告警](#十一监控与告警)
12. [实施路线图](#十二实施路线图)

---

## 一、设计原则

```
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
```

---

## 二、三层引擎架构

```
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
```

---

## 三、引擎抽象层

**文件路径**: `apps/api/app/tools/browser_engine/__init__.py`

```python
"""
浏览器引擎抽象层
支持 invisible_playwright (优先) + browser-use (备用) + HTTP (直连)
"""

from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import structlog

logger = structlog.get_logger()


class EngineType(str, Enum):
    """引擎类型"""
    INVISIBLE_PLAYWRIGHT = "invisible_playwright"
    BROWSER_USE = "browser_use"
    HTTP = "http"
    # ★ 工程化扩展：预留未来引擎类型
    PLAYWRIGHT_DIRECT = "playwright_direct"
    SELENIUM = "selenium"


class EngineStatus(str, Enum):
    """引擎状态"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    # ★ 工程化扩展
    STARTING = "starting"
    COOLDOWN = "cooldown"
    MAINTENANCE = "maintenance"


@dataclass
class EngineCapability:
    """引擎能力描述"""
    engine_type: EngineType
    anti_crawl_level: int           # 1-5，反爬能力等级
    supports_javascript: bool
    supports_cdp: bool
    supports_stealth: bool
    recaptcha_score: float          # reCAPTCHA v3 预期得分
    startup_time_ms: int            # 启动耗时
    memory_mb: int                  # 内存占用
    # ★ 工程化扩展
    max_concurrent_pages: int = 1
    supports_screenshot: bool = True
    version: str = "1.0.0"


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
    # ★ 工程化扩展
    status_code: Optional[int] = None
    duration_ms: Optional[float] = None
    is_fallback: bool = False


class BaseBrowserEngine(ABC):
    """浏览器引擎基类"""

    def __init__(self, config: dict):
        self.config = config
        self._status = EngineStatus.AVAILABLE
        self._consecutive_failures = 0
        self._failure_threshold = 3  # 连续失败阈值

        # ★ 工程化扩展
        self._engine_name = self.__class__.__name__
        self._started_at: Optional[datetime] = None
        self._total_requests = 0
        self._total_success = 0
        self._total_failures = 0
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None

    # ===== 抽象接口（必须实现） =====

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
        """获取页面内容，所有引擎统一接口"""
        pass

    @abstractmethod
    async def execute_script(self, script: str) -> Any:
        """执行 JavaScript"""
        pass

    @abstractmethod
    async def close(self):
        """关闭引擎，释放资源"""
        pass

    # ===== 通用方法 =====

    def record_failure(self):
        """记录失败"""
        self._consecutive_failures += 1
        self._total_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._status = EngineStatus.UNAVAILABLE
            logger.warning(
                f"引擎 {self.engine_type} 标记为不可用",
                failures=self._consecutive_failures,
            )

    def record_success(self):
        """记录成功"""
        self._consecutive_failures = 0
        self._total_success += 1
        self._status = EngineStatus.AVAILABLE

    @property
    def is_available(self) -> bool:
        return self._status != EngineStatus.UNAVAILABLE

    # ★ 工程化扩展方法

    async def warmup(self):
        """预热引擎 — 子类可选实现"""
        self._started_at = datetime.utcnow()

    async def reset(self):
        """重置引擎到初始状态"""
        await self.close()
        self._consecutive_failures = 0
        self._status = EngineStatus.AVAILABLE

    def get_stats(self) -> dict:
        """获取运行时统计"""
        uptime = 0
        if self._started_at:
            uptime = (datetime.utcnow() - self._started_at).total_seconds()
        return {
            "engine_type": self.engine_type.value,
            "status": self._status.value,
            "uptime_seconds": uptime,
            "total_requests": self._total_requests,
            "success_rate": (
                (self._total_success / max(self._total_requests, 1)) * 100
            ),
            "consecutive_failures": self._consecutive_failures,
            "last_error": self._last_error,
        }
```

### 3.1 错误体系（★ 工程化扩展）

```python
# apps/api/app/tools/browser_engine/errors.py
class EngineError(Exception):
    """所有引擎错误的基类"""
    def __init__(self, message: str, engine_type: EngineType,
                 recoverable: bool = True, retry_delay: int = 0):
        self.engine_type = engine_type
        self.recoverable = recoverable
        self.retry_delay = retry_delay
        super().__init__(message)


class EngineUnavailableError(EngineError):
    """引擎不可用（资源耗尽/崩溃）"""
    def __init__(self, engine_type: EngineType, reason: str):
        super().__init__(f"{engine_type.value} 不可用: {reason}",
                        engine_type, recoverable=False)


class EngineTimeoutError(EngineError):
    """引擎操作超时"""
    def __init__(self, engine_type: EngineType, operation: str, timeout: int):
        super().__init__(f"{engine_type.value} {operation} 超时 {timeout}ms",
                        engine_type, recoverable=True, retry_delay=1_000)


class PageCrawlError(EngineError):
    """页面采集错误"""
    def __init__(self, engine_type: EngineType, url: str,
                 status_code: int, message: str):
        super().__init__(f"[{status_code}] {message}", engine_type)
        self.url = url
        self.status_code = status_code
```

---

## 四、InvisiblePlaywright 引擎实现（优先）

**文件路径**: `apps/api/app/tools/browser_engine/engine/invisible_engine.py`

```python
"""
invisible_playwright 引擎实现 — 第一优先级
高反爬平台主力引擎
"""

from .. import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
from typing import Optional
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
```

---

## 五、BrowserUse 引擎实现（备用）

**文件路径**: `apps/api/app/tools/browser_engine/engine/browser_use_engine.py`

```python
"""
browser-use 引擎实现 — 第二优先级（备用）
invisible_playwright 失败时自动降级使用
"""

from .. import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
from typing import Optional
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
```

---

## 六、HTTP 直连引擎（第三优先级）

**文件路径**: `apps/api/app/tools/browser_engine/engine/http_engine.py`

```python
"""
HTTP 直连引擎 — 第三优先级
适用于无反爬或低反爬平台（GitHub API、知乎、掘金等）
"""

from .. import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
from typing import Optional
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
```

---

## 七、引擎调度器（核心）

**文件路径**: `apps/api/app/tools/browser_engine/manager/engine_manager.py`

```python
"""
浏览器引擎管理器
自动选择最优引擎，支持降级策略
核心设计：单例模式
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
```

### 7.1 引擎池扩展（★ 工程化扩展）

```python
# apps/api/app/tools/browser_engine/manager/pool.py
"""
引擎实例池 — 在 EngineManager 单例基础上扩展
解决高并发场景下的引擎复用问题
"""

from .. import EngineType, BaseBrowserEngine
from .engine_manager import EngineManager


class EnginePool:
    """
    引擎池 — 可选扩展，不属于原文核心逻辑
    仅在 EngineManager 单例实例数不足时启用
    """

    def __init__(self, pool_size: int = 2):
        self._pool: dict[EngineType, list[BaseBrowserEngine]] = {}
        self._pool_size = pool_size
        self._manager = EngineManager()  # 获取单例

    async def warmup_all(self):
        """预热所有引擎"""
        for engine_type in EngineType:
            for _ in range(self._pool_size):
                engine = self._manager._get_or_create_engine(engine_type)
                await engine.warmup()
                self._pool.setdefault(engine_type, []).append(engine)
```

### 7.2 引擎生命周期管理（★ 工程化扩展）

```python
# apps/api/app/tools/browser_engine/manager/lifecycle.py
class EngineLifecycleManager:
    """引擎生命周期管理"""

    INIT_ORDER = [
        EngineType.HTTP,
        EngineType.INVISIBLE_PLAYWRIGHT,
        EngineType.BROWSER_USE,
    ]

    async def startup(self):
        """应用启动时调用 — 顺序初始化"""
        for engine_type in self.INIT_ORDER:
            try:
                engine = self._manager._get_or_create_engine(engine_type)
                await engine.warmup()
            except Exception as e:
                logger.error(f"引擎 {engine_type} 启动失败", error=str(e))

    async def shutdown(self, grace_period: int = 30):
        """应用关闭时调用 — 优雅关闭"""
        manager = EngineManager()
        await manager.close_all()

    async def health_check_loop(self, interval: int = 30):
        """定期健康检查循环"""
        while True:
            manager = EngineManager()
            await manager.health_check_all()
            await asyncio.sleep(interval)
```

---

## 八、平台适配器重写（使用引擎管理器）

**文件路径**: `apps/api/app/mcp/adapters/boss_zhipin_v3.py`

```python
"""
BOSS直聘适配器 v3 — 使用引擎管理器
自动选择 invisible_playwright (优先) → browser-use (备用)
"""

from .base import PlatformAdapter, CrawlResult, PlatformStatus
from ..tools.browser_engine.manager.engine_manager import EngineManager, EngineStatus
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
        """解析列表页 — 使用 Scrapling Fetcher"""
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
```

---

## 九、配置更新

### 9.1 原文配置格式（完整保留，直接可用）

```python
# apps/api/app/tools/browser_engine/config.py

# ============ 引擎管理器配置 ============
ENGINE_MANAGER_CONFIG = {
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
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/125.0.0.0 Safari/537.36",
    },
}

# 平台引擎映射（可自定义覆盖）
PLATFORM_ENGINE_MAP_CONFIG = {
    "boss_zhipin": "invisible_playwright",
    "liepin": "invisible_playwright",
    "maimai": "invisible_playwright",
    "linkedin": "invisible_playwright",
    "github": "http",
    "zhihu": "http",
    "juejin": "http",
}
```

### 9.2 Pydantic 验证层（★ 工程化扩展）

```python
from pydantic import BaseModel, Field

class InvisiblePlaywrightSettings(BaseModel):
    cache_dir: str = "~/.cache/invisible_playwright"
    default_seed: str | None = None
    default_pin: dict = {"screen.width": 1920, "screen.height": 1080}
    pool_size: int = Field(2, ge=1, le=10)
    auto_recover: bool = True
    health_check_interval: int = 30

class BrowserUseSettings(BaseModel):
    cdp_url: str = "http://localhost:9222"
    headless: bool = False
    connect_timeout: int = Field(10, ge=1)

class HTTPSettings(BaseModel):
    timeout: float = Field(30.0, ge=1)
    user_agent: str = ENGINE_MANAGER_CONFIG["http"]["user_agent"]
    max_connections: int = Field(50, ge=1)

class EngineManagerSettings(BaseModel):
    invisible_playwright: InvisiblePlaywrightSettings = InvisiblePlaywrightSettings()
    browser_use: BrowserUseSettings = BrowserUseSettings()
    http: HTTPSettings = HTTPSettings()
```

---

## 十、降级策略可视化

```
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
```

---

## 十一、监控与告警

### 11.1 原文任务：带引擎降级监控的采集任务

原文使用 **Celery**，项目使用 **arq**。以下保留原文核心降级检测逻辑，适配 arq。

```python
# apps/api/app/tools/browser_engine/monitoring/crawl_task_v2.py
"""
带引擎降级监控的采集任务
核心降级检测逻辑不变
"""

import structlog
from typing import Optional

logger = structlog.get_logger()


async def crawl_with_engine_monitoring(
    platform_name: str,
    keyword: str,
    task_id: str,
    search_url: str,
) -> dict:
    """
    增强版采集任务 — 记录引擎降级事件
    对应原文 @shared_task(bind=True, max_retries=3)
    """
    from ..manager.engine_manager import EngineManager

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
            url=search_url,
        )
        # TODO: 发送钉钉/企业微信告警

    return {
        "platform": platform_name,
        "engine_used": result.engine_used,
        "success": result.success,
        "html_length": len(result.html) if result.html else 0,
    }
```

### 11.2 Prometheus 指标（★ 工程化扩展）

```python
from prometheus_client import Counter, Histogram, Gauge
import time

engine_requests_total = Counter(
    "engine_requests_total", "Total requests by engine and platform",
    ["engine", "platform", "status"]
)
engine_request_duration = Histogram(
    "engine_request_duration_seconds", "Request latency by engine",
    ["engine", "platform"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60]
)
engine_fallback_total = Counter(
    "engine_fallback_total", "Fallback count by platform",
    ["platform", "from_engine", "to_engine"]
)


async def monitored_fetch(
    engine_manager: EngineManager,
    url: str,
    platform_name: str,
    timeout: int = 30000,
) -> dict:
    """带 Prometheus 指标采集的 fetch 包装"""
    preferred = engine_manager.get_preferred_engine(platform_name)
    start = time.monotonic()

    result = await engine_manager.fetch_with_fallback(
        url=url, platform_name=platform_name, timeout=timeout
    )

    duration = time.monotonic() - start
    actual_engine = result.engine_used.value if result.engine_used else "none"

    engine_requests_total.labels(
        engine=actual_engine, platform=platform_name,
        status="success" if result.success else "failed"
    ).inc()
    engine_request_duration.labels(
        engine=actual_engine, platform=platform_name
    ).observe(duration)

    if actual_engine != preferred.value:
        engine_fallback_total.labels(
            platform=platform_name,
            from_engine=preferred.value,
            to_engine=actual_engine,
        ).inc()

    return result
```

### 11.3 事件总线 + 告警（★ 工程化扩展）

```python
# apps/api/app/tools/browser_engine/monitoring/events.py
class EngineEvent(str, Enum):
    ENGINE_STARTED = "engine.started"
    ENGINE_STOPPED = "engine.stopped"
    ENGINE_DEGRADED = "engine.degraded"
    ENGINE_RECOVERED = "engine.recovered"
    FETCH_SUCCESS = "fetch.success"
    FETCH_FAILED = "fetch.failed"
    FALLBACK_TRIGGERED = "fallback.triggered"
    PAGE_BLOCKED = "page.blocked"
    CAPTCHA_DETECTED = "captcha.detected"


class EventBus:
    """事件总线 — 引擎事件的发布/订阅"""

    _handlers: dict[EngineEvent, list[Callable]] = {}

    @classmethod
    def subscribe(cls, event: EngineEvent, handler: Callable):
        cls._handlers.setdefault(event, []).append(handler)

    @classmethod
    async def publish(cls, event: EngineEvent, **data):
        for handler in cls._handlers.get(event, []):
            try:
                await handler(event, **data)
            except Exception as e:
                logger.error(f"事件处理器失败", event=event, error=str(e))
```

---

## 十二、实施路线图

### 原文 Phase（完整保留）

| 阶段 | 任务 | 时间 | 说明 |
|------|------|------|------|
| **Phase 0** | 安装 invisible_playwright，验证 macOS | 30 分钟 | `pip install` + `fetch` + 清除隔离属性 |
| **Phase 1** | 实现引擎抽象层 + 三个引擎 | 1 天 | BaseBrowserEngine + Invisible + BrowserUse + HTTP |
| **Phase 2** | 实现引擎管理器 + 降级逻辑 | 半天 | EngineManager + fallback 策略 |
| **Phase 3** | 重写 BOSS直聘适配器（v3） | 半天 | 使用引擎管理器 |
| **Phase 4** | 对比测试 | 半天 | invisible vs browser-use vs HTTP |
| **Phase 5** | 重写猎聘/脉脉适配器 | 1 天 | 复用引擎管理器 |
| **Phase 6** | **删除冗余反爬代码** | 半天 | **删除 mouse_simulator 等** |
| **Phase 7** | 监控告警 + 文档 | 半天 | 降级事件告警 |

### Phase 6 清理清单

- [ ] `mouse_simulator.py` — 不再需要，invisible_playwright 内置贝塞尔鼠标
- [ ] `fingerprint_generator.py` — 不再需要，invisible_playwright 内置相干指纹
- [ ] `stealth_utils.py` — 不再需要，invisible_playwright 内置
- [ ] `captcha_solver.py` 中的滑块轨迹部分 — 改为统一打码服务调用

### 工程化扩展 Phase（在原文 Phase 之上叠加）

| 阶段 | 任务 | 时间 | 说明 |
|------|------|------|------|
| **Phase E1** | 错误体系 + 中间件管道 | 1 天 | errors.py + 4 个内置中间件 |
| **Phase E2** | 引擎池 + 生命周期管理 | 1 天 | EnginePool + lifecycle + 健康检查循环 |
| **Phase E3** | Prometheus 指标 + Grafana 面板 | 1 天 | 可观测性基础设施 |
| **Phase E4** | 事件总线 + 钉钉/企微告警 | 半天 | 降级事件自动告警 |
| **Phase E5** | 插件注册表 + 插件开发指南 | 1 天 | 可扩展性基础设施 |

---

## 附录：Momus 修正对照表

| 原文需求 | 规划原有问题 | 修正状态 |
|----------|-------------|---------|
| EngineManager 单例模式 | 被 pool-based 替换 | ❌→✅ 保留 `__new__`/`_initialized` |
| 降级策略可视化 | 完全缺失 | ❌→✅ 复刻 ASCII 8 步流程图 |
| 原文精确 Python 代码 | 被抽象描述替代 | ❌→✅ 每个文件完整代码 |
| Scrapling Fetcher 集成 | 未体现 | ❌→✅ `from scrapling import Fetcher` |
| Phase 6 删除冗余代码 | 完全遗漏 | ❌→✅ mouse_simulator 等清理清单 |
| 项目路径适配 | 路径错误 | ❌→✅ `apps/api/app/tools/browser_engine/` |
| 监控告警任务代码 | 被通用 Prometheus 替代 | ❌→✅ 保留原文逻辑 + arq 适配 |
| 配置格式 | 被 Pydantic 替代 | ❌→✅ 原文字典 + Pydantic 双层保留 |
| 平台适配器完整代码 | 被简化 | ❌→✅ BossZhipinAdapterV3 完整复刻 |

---

## TODOs：实施任务清单

### Phase 0：环境搭建

- [ ] **Phase 0.1**: 安装 invisible_playwright 并验证 macOS 可用性 — `pip install` + fetch 测试
- [ ] **Phase 0.2**: 安装 browser-use 及项目依赖（structlog / httpx / scrapling / prometheus-client）
- [ ] **Phase 0.3**: 创建 `browser_engine/` 目录结构（engine/ manager/ middleware/ monitoring/ plugins/ tests/）

### Phase 1：引擎抽象层 + 三个引擎

- [ ] **Phase 1.1**: 实现 `__init__.py` — EngineType / EngineStatus / EngineCapability / PageResult / BaseBrowserEngine
- [ ] **Phase 1.2**: 实现 `errors.py` — EngineError 分层体系（UnavailableError / TimeoutError / PageCrawlError）
- [ ] **Phase 1.3**: 实现 `engine/http_engine.py` — HTTPEngine（httpx.AsyncClient + 原文完整代码）
- [ ] **Phase 1.4**: 实现 `engine/invisible_engine.py` — InvisiblePlaywrightEngine（原文完整代码 + \_\_enter\_\_ 模式）
- [ ] **Phase 1.5**: 实现 `engine/browser_use_engine.py` — BrowserUseEngine（原文完整代码 + Agent llm=None）
- [ ] **Phase 1.6**: 编写三个引擎的单元测试（接口契约测试 + record_failure/record_success 逻辑）

### Phase 2：引擎管理器 + 降级逻辑

- [ ] **Phase 2.1**: 实现 `manager/engine_manager.py` — EngineManager 单例模式 + PLATFORM_ENGINE_MAP + EngineFallbackChain
- [ ] **Phase 2.2**: 实现 `manager/engine_manager.py` — fetch_with_fallback 降级链（首选→备用→HTTP 去重）
- [ ] **Phase 2.3**: 实现 `manager/engine_manager.py` — health_check_all + close_all + _get_or_create_engine
- [ ] **Phase 2.4**: 实现 `manager/pool.py` — EnginePool 引擎实例池（可选扩展，不替换单例）
- [ ] **Phase 2.5**: 实现 `manager/lifecycle.py` — EngineLifecycleManager（启动预热 + 优雅关闭 + 健康检查循环）
- [ ] **Phase 2.6**: 实现 `config.py` — 原文字典格式配置 + Pydantic Settings 验证层
- [ ] **Phase 2.7**: 编写 EngineManager 降级链测试（首选成功 / 首选失败降级 / 全部失败 / mock 引擎）

### Phase 3：BOSS 直聘适配器 v3

- [ ] **Phase 3.1**: 实现 BossZhipinAdapterV3 — \_\_init\_\_ + health_check（使用 EngineManager）
- [ ] **Phase 3.2**: 实现 BossZhipinAdapterV3 — search + parse_list_page（Scrapling Fetcher + 字段映射）
- [ ] **Phase 3.3**: 实现 BossZhipinAdapterV3 — get_detail + _build_search_url + cleanup
- [ ] **Phase 3.4**: 编写 BossZhipinAdapterV3 测试（mock EngineManager + HTML fixture 解析）

### Phase 4：对比测试

- [ ] **Phase 4.1**: 编写对比测试 harness（同一 URL 三引擎依次测试，记录成功率 / 耗时 / 内存）
- [ ] **Phase 4.2**: 执行对比测试并输出报告（invisible vs browser-use vs HTTP 各项指标）

### Phase 5：多平台扩展

- [ ] **Phase 5.1**: 实现猎聘适配器 LiepinAdapter（复用 EngineManager）
- [ ] **Phase 5.2**: 实现脉脉适配器 MaimaiAdapter（复用 EngineManager）

### Phase 6：删除冗余反爬代码

- [ ] **Phase 6.1**: 删除 `mouse_simulator.py` — invisible_playwright 已内置贝塞尔鼠标
- [ ] **Phase 6.2**: 删除 `fingerprint_generator.py` + `stealth_utils.py` — invisible_playwright 已内置
- [ ] **Phase 6.3**: 清理 `captcha_solver.py` 中滑块轨迹部分 — 改为统一打码服务调用

### Phase 7：监控告警 + 文档

- [ ] **Phase 7.1**: 实现 `monitoring/crawl_task_v2.py` — 降级监控 + 告警日志（原文 Celery → arq 适配）
- [ ] **Phase 7.2**: 实现 `monitoring/metrics.py` — Prometheus 指标（requests_total / duration / fallback_total）
- [ ] **Phase 7.3**: 实现 `monitoring/events.py` + EventBus — 引擎事件发布/订阅，支持钉钉/企微告警
- [ ] **Phase 7.4**: 实现 `monitoring/health.py` — 健康检查端点 GET /api/v1/sourcing/engine-health

### Phase E1：中间件管道（工程化扩展）

- [ ] **Phase E1.1**: 实现 `middleware/base.py` — EngineMiddleware 基类 + 管道注册机制
- [ ] **Phase E1.2**: 实现内置中间件（retry 重试 + timeout 超时 + proxy_selector 代理选择 + metrics_collector 指标）

### Phase E2：引擎池 + 生命周期（工程化扩展）

- [ ] **Phase E2.1**: 完成 EnginePool 集成测试（池化 / 借用归还 / 自动扩缩 / 健康检测）

### Phase E3：可观测性基础设施（工程化扩展）

- [ ] **Phase E3.1**: 配置 Prometheus + Grafana 面板（引擎请求量 / 成功率 / 降级率 / 延迟分布）

### Phase E4：告警体系（工程化扩展）

- [ ] **Phase E4.1**: 实现钉钉/企业微信告警 webhook（降级事件自动推送）

### Phase E5：插件系统（工程化扩展）

- [ ] **Phase E5.1**: 实现 `plugins/registry.py` + `plugins/base.py` — 引擎插件注册表 + EnginePlugin 基类
- [ ] **Phase E5.2**: 实现内置插件（screenshot_capture 调试截图 + request_recorder 请求录制）
- [ ] **Phase E5.3**: 编写引擎开发指南 + 插件开发指南文档

### Phase 终验

- [ ] **Phase 终验**: 全栈验证 — 创建采集任务 → 引擎自动选择 → 页面获取 → 降级链 → 指标输出
