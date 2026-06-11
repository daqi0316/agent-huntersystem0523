"""Sourcing 专属配置"""
from pydantic_settings import BaseSettings


class SourcingSettings(BaseSettings):
    # Playwright CDP
    playwright_headless: bool = True
    playwright_cdp_port: int = 9222
    playwright_browser_path: str | None = None

    # 代理池
    proxy_premium_url: str = ""
    proxy_standard_url: str = ""
    proxy_mobile_url: str = ""
    proxy_pool_min_size: int = 5
    proxy_pool_max_size: int = 50

    # 打码服务
    captcha_service: str = "none"
    captcha_api_key: str = ""

    # 采集限制
    max_candidates_per_task: int = 500
    default_rate_limit: int = 3
    max_concurrent_tasks: int = 5
    max_retries: int = 3
    task_timeout_seconds: int = 3600

    # GitHub Token（用于 GitHub 适配器）
    github_token: str = ""

    # AI 分析
    ai_analysis_enabled: bool = True
    ai_analysis_model: str = "default"
    ai_analysis_batch_size: int = 10

    # 去重
    dedup_redis_ttl_days: int = 30
    dedup_refresh_days: int = 7

    # Redis
    redis_url: str = "redis://localhost:6379/2"

    # arq 队列
    arq_redis_db: int = 2
    arq_max_tries: int = 3
    arq_job_timeout: int = 3600
    arq_concurrency: int = 2

    model_config = {"env_prefix": "SOURCING_", "env_file": ".env", "extra": "ignore"}


sourcing_settings = SourcingSettings()
