"""
引擎配置体系
原文字典格式（完整保留，直接可用）+ Pydantic Settings 验证层（工程化扩展）
"""

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

# ★ 工程化扩展：Pydantic 验证层
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


__all__ = [
    "ENGINE_MANAGER_CONFIG",
    "PLATFORM_ENGINE_MAP_CONFIG",
    "EngineManagerSettings",
    "InvisiblePlaywrightSettings",
    "BrowserUseSettings",
    "HTTPSettings",
]
