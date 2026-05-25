"""LLM factory: config-driven client selection."""

from app.core.config import settings
from app.llm.base import LLMClient
from app.llm.omlx_client import OMLXClient
from app.llm.vllm_client import VLLMClient

__all__ = ["LLMClient", "VLLMClient", "OMLXClient", "get_llm_client"]


def get_llm_client() -> LLMClient:
    """Return the configured LLM client based on settings.llm_provider."""
    provider = settings.llm_provider.lower()
    if provider == "vllm":
        return VLLMClient()
    return OMLXClient()
