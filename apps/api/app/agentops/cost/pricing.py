"""模型定价配置 — 可插拔，后续可迁移到 DB 表 + 管理界面。

用法:
    from app.agentops.cost.pricing import get_model_pricing, calculate_cost

    # 查询定价
    pricing = get_model_pricing("gpt-4o")  # → ModelPricing or None

    # 计算成本
    cost = calculate_cost("gpt-4o", prompt_tokens=100, completion_tokens=50)
"""
from __future__ import annotations

from typing import Final

from pydantic import BaseModel


class ModelPricing(BaseModel):
    """单模型的定价规则。"""

    input_token_cost_per_1k: float
    """每 1000 个 prompt token 的成本（USD）。"""

    output_token_cost_per_1k: float
    """每 1000 个 completion token 的成本（USD）。"""

    currency: str = "USD"

    def calculate(self, prompt_tokens: int, completion_tokens: int) -> float:
        """计算本次调用的估算成本。"""
        input_cost = (prompt_tokens / 1000) * self.input_token_cost_per_1k
        output_cost = (completion_tokens / 1000) * self.output_token_cost_per_1k
        return round(input_cost + output_cost, 6)


# ---------------------------------------------------------------------------
# 默认定价表 — 基于各模型官方公开定价（2026-06 版）
# key: model name（支持前缀匹配 fallback）
# value: ModelPricing
# ---------------------------------------------------------------------------
_MODEL_PRICING: dict[str, ModelPricing] = {
    # ---- OpenAI ----
    "gpt-4o": ModelPricing(
        input_token_cost_per_1k=0.0025,
        output_token_cost_per_1k=0.0100,
    ),
    "gpt-4o-mini": ModelPricing(
        input_token_cost_per_1k=0.00015,
        output_token_cost_per_1k=0.00060,
    ),
    "gpt-4-turbo": ModelPricing(
        input_token_cost_per_1k=0.0100,
        output_token_cost_per_1k=0.0300,
    ),
    "gpt-4": ModelPricing(
        input_token_cost_per_1k=0.0300,
        output_token_cost_per_1k=0.0600,
    ),
    "gpt-3.5-turbo": ModelPricing(
        input_token_cost_per_1k=0.0005,
        output_token_cost_per_1k=0.0015,
    ),
    "o1": ModelPricing(
        input_token_cost_per_1k=0.0150,
        output_token_cost_per_1k=0.0600,
    ),
    "o1-mini": ModelPricing(
        input_token_cost_per_1k=0.0030,
        output_token_cost_per_1k=0.0120,
    ),
    "o3-mini": ModelPricing(
        input_token_cost_per_1k=0.0010,
        output_token_cost_per_1k=0.0040,
    ),
    # ---- Anthropic ----
    "claude-3-5-sonnet": ModelPricing(
        input_token_cost_per_1k=0.0030,
        output_token_cost_per_1k=0.0150,
    ),
    "claude-3-5-haiku": ModelPricing(
        input_token_cost_per_1k=0.00080,
        output_token_cost_per_1k=0.0040,
    ),
    "claude-3-opus": ModelPricing(
        input_token_cost_per_1k=0.0150,
        output_token_cost_per_1k=0.0750,
    ),
    "claude-4-sonnet": ModelPricing(
        input_token_cost_per_1k=0.0030,
        output_token_cost_per_1k=0.0150,
    ),
    # ---- Google ----
    "gemini-2.5-pro": ModelPricing(
        input_token_cost_per_1k=0.00125,
        output_token_cost_per_1k=0.00500,
    ),
    "gemini-2.0-flash": ModelPricing(
        input_token_cost_per_1k=0.00010,
        output_token_cost_per_1k=0.00040,
    ),
    # ---- DeepSeek ----
    "deepseek-v3": ModelPricing(
        input_token_cost_per_1k=0.0010,
        output_token_cost_per_1k=0.0040,
    ),
    "deepseek-r1": ModelPricing(
        input_token_cost_per_1k=0.0055,
        output_token_cost_per_1k=0.0022,
    ),
    # ---- Local (zero-cost) ----
    "Qwen": ModelPricing(
        input_token_cost_per_1k=0.0,
        output_token_cost_per_1k=0.0,
    ),
    "qwen": ModelPricing(
        input_token_cost_per_1k=0.0,
        output_token_cost_per_1k=0.0,
    ),
    "llama": ModelPricing(
        input_token_cost_per_1k=0.0,
        output_token_cost_per_1k=0.0,
    ),
    "phi": ModelPricing(
        input_token_cost_per_1k=0.0,
        output_token_cost_per_1k=0.0,
    ),
    "gemma": ModelPricing(
        input_token_cost_per_1k=0.0,
        output_token_cost_per_1k=0.0,
    ),
    "mistral": ModelPricing(
        input_token_cost_per_1k=0.0,
        output_token_cost_per_1k=0.0,
    ),
}

_DEFAULT_FALLBACK: Final[ModelPricing] = ModelPricing(
    input_token_cost_per_1k=0.0,
    output_token_cost_per_1k=0.0,
    currency="USD",
)


def get_model_pricing(model: str) -> ModelPricing:
    """查找模型定价。支持精确匹配和前缀匹配。

    精确匹配优先，没有精确匹配时按前缀匹配（第一个匹配返回）。
    完全找不到时返回 0 成本 fallback（本地模型），不报错。
    """
    exact = _MODEL_PRICING.get(model)
    if exact is not None:
        return exact

    # 前缀匹配
    for key, pricing in _MODEL_PRICING.items():
        if model.startswith(key):
            return pricing

    return _DEFAULT_FALLBACK


def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """计算单次 LLM 调用的估算成本。"""
    pricing = get_model_pricing(model)
    return pricing.calculate(prompt_tokens, completion_tokens)


def get_known_models() -> list[dict]:
    """返回已知模型列表（用于前端展示定价表）。"""
    return [
        {"model": m, **p.model_dump()}
        for m, p in sorted(_MODEL_PRICING.items())
    ]
