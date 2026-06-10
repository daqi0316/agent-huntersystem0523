import logging
import os

from pydantic import Field
from pydantic_settings import BaseSettings


logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # App
    app_name: str = "AI Recruitment System"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_recruitment"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/ai_recruitment"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "resumes"
    qdrant_memory_collection: str = "session_summaries"
    qdrant_vector_size: int | None = None  # auto-detected at runtime if None

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "resumes"

    # JWT — min 32 characters for production safety
    jwt_secret: str = Field(
        default="your-jwt-secret-change-in-production",
        min_length=32,
        description="JWT signing key; must be >= 32 chars in production",
    )
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # LLM
    llm_provider: str = "omlx"
    llm_base_url: str = "http://localhost:8000/v1"
    llm_api_key: str = "sk-no-key-required"
    llm_model: str = "Qwen3.6-35B-A3B-4bit"
    llm_embed_model: str = "bge-m3-mlx-4bit"

    qweather_api_key: str = ""
    qweather_api_host: str = ""

    # JD Generator
    jd_gen_max_iterations: int = 6
    jd_gen_threshold: float = 7.0

    # CORS
    cors_origins: list[str] = [f"http://localhost:{p}" for p in range(3000, 3011)]

    langgraph_pg_dsn: str | None = None

    use_orchestrator_graph: bool = False

    wechat_corp_id: str = ""
    wechat_corp_agent_id: str = ""
    wechat_corp_secret: str = ""
    wechat_oauth_redirect_uri: str = "http://localhost:3000/api/auth/wechat/callback"
    wechat_qrcode_expire_seconds: int = 600
    wechat_mock_mode: bool = True
    wechat_template_id: str = ""
    wechat_template_miniprogram_appid: str = ""

    dingtalk_corp_id: str = ""
    dingtalk_agent_id: str = ""
    dingtalk_app_secret: str = ""
    dingtalk_oauth_redirect_uri: str = "http://localhost:3000/api/auth/dingtalk/callback"
    dingtalk_qrcode_expire_seconds: int = 600
    dingtalk_mock_mode: bool = True

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_oauth_redirect_uri: str = "http://localhost:3000/api/auth/feishu/callback"
    feishu_qrcode_expire_seconds: int = 600
    feishu_mock_mode: bool = True

    wecom_corp_id: str = ""
    wecom_agent_id: str = ""
    wecom_secret: str = ""
    wecom_oauth_redirect_uri: str = "http://localhost:3000/api/auth/wecom/callback"
    wecom_qrcode_expire_seconds: int = 600
    wecom_mock_mode: bool = True

    rate_limit_org_per_min: int = 100
    rate_limit_user_per_min: int = 60
    rate_limit_ip_per_min: int = 30
    rate_limit_rollout_pct: int = 100
    quota_alert_threshold_pct: int = 80

    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""
    aliyun_sms_sign_name: str = "AI Recruitment"
    aliyun_sms_template_code: str = "SMS_000000001"
    aliyun_sms_region: str = "cn-hangzhou"
    sms_mock_mode: bool = True
    invite_max_per_ip_24h: int = 3
    invite_max_per_device_24h: int = 5
    llm_circuit_breaker_enabled: bool = True

    agentops_enabled: bool = False
    agentops_provider: str = "noop"
    agentops_environment: str = "local"
    agentops_queue_max_size: int = 1000
    agentops_flush_timeout_seconds: float = 2.0
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = ""
    langfuse_capture_input: bool = False
    langfuse_capture_output: bool = False

    wechat_pay_merchant_id: str = ""
    wechat_pay_api_key: str = ""
    wechat_pay_cert_path: str = ""
    wechat_pay_key_path: str = ""
    alipay_app_id: str = ""
    alipay_private_key_path: str = ""
    alipay_public_key_path: str = ""
    payment_notify_base_url: str = "https://api.airecruit.com"
    payment_order_expire_minutes: int = 30
    payment_mock_mode: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}

    def check_production_readiness(self) -> list[str]:
        """Return a list of warnings about potentially unsafe production defaults."""
        warnings: list[str] = []
        if self.debug and not os.getenv("DEBUG"):
            warnings.append("debug=True in production — set DEBUG=false in .env")
        if self.jwt_secret == "your-jwt-secret-change-in-production":
            warnings.append("jwt_secret is still the default value — set JWT_SECRET in .env")
        if self.database_url == "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_recruitment":
            warnings.append("database_url uses default local credentials — set DATABASE_URL in .env")
        if self.cors_origins == ["http://localhost:3000"]:
            warnings.append("cors_origins is set to localhost only — configure CORS_ORIGINS for production")
        return warnings


settings = Settings()

# Log production readiness warnings on import
if not settings.debug:
    for w in settings.check_production_readiness():
        logger.warning("PRODUCTION: %s", w)
