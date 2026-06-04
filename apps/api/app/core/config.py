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

    # JD Generator
    jd_gen_max_iterations: int = 6
    jd_gen_threshold: float = 7.0

    # CORS
    cors_origins: list[str] = [f"http://localhost:{p}" for p in range(3000, 3011)]

    langgraph_pg_dsn: str | None = None

    use_orchestrator_graph: bool = False

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
