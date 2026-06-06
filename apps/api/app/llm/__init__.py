"""LLM factory: config-driven client selection."""

from app.core.config import settings
from app.llm.base import LLMClient
from app.llm.cn_providers import (
    CN_PROVIDERS,
    DeepSeekClient,
    QwenClient,
    ZhipuClient,
    get_cn_llm_client,
    list_supported_providers,
)
from app.llm.omlx_client import OMLXClient
from app.llm.vllm_client import VLLMClient

__all__ = [
    "LLMClient",
    "VLLMClient",
    "OMLXClient",
    "QwenClient",
    "DeepSeekClient",
    "ZhipuClient",
    "CN_PROVIDERS",
    "get_llm_client",
    "get_cn_llm_client",
    "list_supported_providers",
]


def get_llm_client() -> LLMClient:
    """Return the configured LLM client based on settings.llm_provider.

    支持: omlx / vllm / qwen / deepseek / zhipu
    """
    provider = settings.llm_provider.lower()
    if provider == "vllm":
        return VLLMClient()
    if provider in ("omlx", ""):
        return OMLXClient()
    if provider in CN_PROVIDERS:
        return get_cn_llm_client(provider)
    raise ValueError(
        f"Unknown LLM provider: {provider}. "
        f"Supported: omlx/vllm/{'/'.join(CN_PROVIDERS.keys())}"
    )
