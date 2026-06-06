"""P6-8 跨 phase 技术债: 国内 LLM 接入 — 4 provider, OpenAI-compatible 模式。

PIPL 合规: 客户数据不向境外传输。
国内 LLM 通过 OpenAI-compatible 协议 (与 omlx/vllm 同) 实现 0 改接入:

- 通义千问 (DashScope, OpenAI-compat)
- DeepSeek (api.deepseek.com, OpenAI-compat)
- 智谱 GLM (open.bigmodel.cn, OpenAI-compat)
- 文心一言 (千帆, 需走自有 SDK — 部分功能)

使用: 配 LLM_PROVIDER=qwen/deepseek/zhipu/wenxin + 对应 API_KEY。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings
from app.llm.base import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class CNProviderConfig:
    name: str
    base_url: str
    api_key_env: str
    default_model: str
    openai_compat: bool = True


CN_PROVIDERS: dict[str, CNProviderConfig] = {
    "qwen": CNProviderConfig(
        name="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="QWEN_API_KEY",
        default_model="qwen-plus",
        openai_compat=True,
    ),
    "deepseek": CNProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        openai_compat=True,
    ),
    "zhipu": CNProviderConfig(
        name="zhipu",
        base_url="https://open.bigmodel.cn/api/paas/v4/",
        api_key_env="ZHIPU_API_KEY",
        default_model="glm-4-plus",
        openai_compat=True,
    ),
}


class QwenClient(LLMClient):
    """通义千问 — DashScope OpenAI-compatible mode。"""

    def __init__(self) -> None:
        self.provider = CN_PROVIDERS["qwen"]
        self.model = settings.llm_model or self.provider.default_model
        self.client = AsyncOpenAI(
            api_key=getattr(settings, "qwen_api_key", "") or self._get_key(),
            base_url=self.provider.base_url,
        )

    def _get_key(self) -> str:
        import os
        return os.getenv(self.provider.api_key_env, "")

    async def chat(self, messages, **kw):
        return await self.client.chat.completions.create(
            model=self.model, messages=messages, **kw,
        )

    async def embed(self, text: str) -> list[float]:
        resp = await self.client.embeddings.create(
            model="text-embedding-v3", input=text,
        )
        return list(resp.data[0].embedding)


class DeepSeekClient(LLMClient):
    """DeepSeek — api.deepseek.com OpenAI-compatible。"""

    def __init__(self) -> None:
        self.provider = CN_PROVIDERS["deepseek"]
        self.model = settings.llm_model or self.provider.default_model
        import os
        self.client = AsyncOpenAI(
            api_key=getattr(settings, "deepseek_api_key", "") or os.getenv(self.provider.api_key_env, ""),
            base_url=self.provider.base_url,
        )

    async def chat(self, messages, **kw):
        return await self.client.chat.completions.create(
            model=self.model, messages=messages, **kw,
        )

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("DeepSeek 当前不提供 embed API, 用通义/智谱替代")


class ZhipuClient(LLMClient):
    """智谱 GLM — open.bigmodel.cn OpenAI-compatible (glm-4-plus / glm-4-flash)。"""

    def __init__(self) -> None:
        self.provider = CN_PROVIDERS["zhipu"]
        self.model = settings.llm_model or self.provider.default_model
        import os
        self.client = AsyncOpenAI(
            api_key=getattr(settings, "zhipu_api_key", "") or os.getenv(self.provider.api_key_env, ""),
            base_url=self.provider.base_url,
        )

    async def chat(self, messages, **kw):
        return await self.client.chat.completions.create(
            model=self.model, messages=messages, **kw,
        )

    async def embed(self, text: str) -> list[float]:
        resp = await self.client.embeddings.create(
            model="embedding-2", input=text,
        )
        return list(resp.data[0].embedding)


def get_cn_llm_client(provider: Optional[str] = None) -> LLMClient:
    """根据 settings.llm_provider (或参数) 返国内 LLM client。

    抛 ValueError 当 provider 不支持。
    """
    p = (provider or settings.llm_provider).lower()
    if p == "qwen":
        return QwenClient()
    if p == "deepseek":
        return DeepSeekClient()
    if p == "zhipu":
        return ZhipuClient()
    raise ValueError(
        f"Unknown CN LLM provider: {p}. "
        f"Supported: {list(CN_PROVIDERS.keys())}"
    )


def list_supported_providers() -> list[dict]:
    return [
        {
            "name": c.name,
            "base_url": c.base_url,
            "env_key": c.api_key_env,
            "default_model": c.default_model,
            "openai_compat": c.openai_compat,
        }
        for c in CN_PROVIDERS.values()
    ]
