"""BaseProvider — 模型提供者抽象基类 + 错误分类体系。

提供统一的 Provider 接口（chat / chat_stream / embed / check_connection）和
错误分类策略矩阵（什么错误可重试、什么错误可降级）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, TypedDict


# ── 类型定义 ──


class ChatResult(TypedDict):
    """统一 LLM 调用返回。"""
    content: str
    model: str
    usage: dict | None
    provider: str


class ConnectionResult(TypedDict):
    """连通性测试结果。"""
    success: bool
    latency_ms: int
    model: str
    error: str | None


# ── 错误分类 ──


class ErrorCategory(Enum):
    """Provider 错误分类 — 每种错误有对应的处理策略。"""
    AUTH = "auth"                   # API Key 错误 → 不重试、不降级
    RATE_LIMIT = "rate_limit"       # 限流 → 退避重试、不降级
    TIMEOUT = "timeout"             # 超时 → 重试、可降级
    SERVER_ERROR = "server_error"   # 5xx → 重试、可降级
    INVALID_MODEL = "invalid_model" # 模型不存在 → 不重试
    CONTEXT_TOO_LONG = "context_too_long"
    UNKNOWN = "unknown"


@dataclass
class Strategy:
    """错误处理策略。"""
    retryable: bool      # 可重试
    fallback: bool       # 可降级到备用模型
    alert: bool          # 需要告警


# 策略矩阵
STRATEGY: dict[ErrorCategory, Strategy] = {
    ErrorCategory.AUTH:             Strategy(retryable=False, fallback=False, alert=True),
    ErrorCategory.RATE_LIMIT:       Strategy(retryable=True,  fallback=False, alert=False),
    ErrorCategory.TIMEOUT:          Strategy(retryable=True,  fallback=True,  alert=False),
    ErrorCategory.SERVER_ERROR:     Strategy(retryable=True,  fallback=True,  alert=True),
    ErrorCategory.INVALID_MODEL:    Strategy(retryable=False, fallback=False, alert=True),
    ErrorCategory.CONTEXT_TOO_LONG: Strategy(retryable=False, fallback=True,  alert=False),
    ErrorCategory.UNKNOWN:          Strategy(retryable=False, fallback=True,  alert=True),
}


class ProviderError(Exception):
    """Provider 调用异常 — 携带错误分类 + 处理策略。"""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        status_code: int | None = None,
        provider: str | None = None,
    ):
        self.category = category
        self.message = message
        self.status_code = status_code
        self.provider = provider
        super().__init__(self.__str__())

    def should_retry(self) -> bool:
        """此错误是否值得重试。"""
        return STRATEGY.get(self.category, STRATEGY[ErrorCategory.UNKNOWN]).retryable

    def should_fallback(self) -> bool:
        """此错误是否应该降级到备用模型。"""
        return STRATEGY.get(self.category, STRATEGY[ErrorCategory.UNKNOWN]).fallback

    def should_alert(self) -> bool:
        """此错误是否需要触发告警。"""
        return STRATEGY.get(self.category, STRATEGY[ErrorCategory.UNKNOWN]).alert

    def __str__(self) -> str:
        return f"[{self.category.value}] {self.message}"


# ── Provider 抽象基类 ──


class BaseProvider(ABC):
    """模型提供者抽象基类。

    所有 Provider（OpenAI-compat / Anthropic / Google 等）继承此类。
    """

    provider_type: str = ""  # 子类覆盖

    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: list[dict],
        **kwargs,
    ) -> ChatResult:
        """调用 LLM chat/completion API。

        参数:
            model: 模型名（如 "deepseek-chat"）
            messages: OpenAI 格式的消息列表
            **kwargs: 透传给 API 的参数（temperature, max_tokens, tools...）

        返回:
            ChatResult（content + model + usage）

        异常:
            ProviderError 携带分类信息
        """
        ...

    async def chat_stream(
        self,
        model: str,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式调用 LLM API（可选覆盖，默认不实现）。

        返回 content 片段的 AsyncIterator。
        """
        raise NotImplementedError(f"{self.provider_type} does not support streaming")
        # 让出类型检查
        if False:
            yield

    async def embed(
        self,
        model: str,
        texts: list[str],
    ) -> list[list[float]]:
        """文本向量化。默认不支持（抛出 NotImplementedError）。

        调用方（Router）应检查 capabilities 或捕获 NotImplementedError 做降级。
        """
        raise NotImplementedError(f"{self.provider_type} does not support embedding")

    @abstractmethod
    async def check_connection(self, model: str, api_key: str | None, base_url: str) -> ConnectionResult:
        """测试 API 连通性 + Key 有效性。

        发一条简短消息看 API 是否正常回复。
        """
        ...
