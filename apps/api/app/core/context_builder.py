"""ContextBuilder — 统一组装 LLM Prompt 的所有材料.

组成（按注入顺序）:
  1. System Prompt (静态模板)
  2. 跨会话记忆上下文 (SummaryService narrative + MemoryFactService structured)
  3. 当前会话历史 (按 token 预算动态裁剪)
  4. 二次推理时追加: assistant turn + tool results

非阻塞设计: 任何子步骤异常均记录日志并返回最小可用内容,
不影响主链路.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.llm.base import LLMClient
    from app.services.qdrant_service import QdrantService

from app.core.config import settings
from app.core.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = getattr(settings, "llm_context_window", 120_000)
SYSTEM_TOKENS = getattr(settings, "system_prompt_tokens", 4000)
MEMORY_TOKENS = getattr(settings, "memory_injection_tokens", 3000)
TOOL_RESULT_TOKENS = getattr(settings, "tool_result_tokens", 8000)
HISTORY_BUDGET = DEFAULT_MAX_TOKENS - SYSTEM_TOKENS - MEMORY_TOKENS
TOOL_RESULT_HISTORY_BUDGET = DEFAULT_MAX_TOKENS - SYSTEM_TOKENS - TOOL_RESULT_TOKENS

_ENCODING_CACHE: dict[str, object] = {}


def _get_encoding(model: str):
    if model in _ENCODING_CACHE:
        return _ENCODING_CACHE[model]
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model(model)
    except Exception:
        import tiktoken
        try:
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            enc = None
    _ENCODING_CACHE[model] = enc
    return enc


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    enc = _get_encoding(model)
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return int(len(text) * 1.5)


def count_message_tokens(msg: dict, model: str = "gpt-4o") -> int:
    role = msg.get("role", "")
    content = msg.get("content", "") or ""
    overhead = 4
    if role:
        overhead += len(role)
    return count_tokens(content, model) + overhead


def count_messages_tokens(msgs: list[dict], model: str = "gpt-4o") -> int:
    return sum(count_message_tokens(m, model) for m in msgs)


class ContextBuilder:
    __slots__ = ("db", "llm", "qdrant", "model")

    def __init__(
        self,
        db: AsyncSession,
        llm: LLMClient,
        qdrant: QdrantService,
        model: str | None = None,
    ) -> None:
        self.db = db
        self.llm = llm
        self.qdrant = qdrant
        self.model = model or getattr(llm, "model", "gpt-4o")

    async def build(self, user_id: str, messages: list[dict]) -> list[dict]:
        system = await self._build_system(user_id)
        history = await self._build_history(messages)
        return [system] + history

    async def build_with_tools(
        self,
        user_id: str,
        messages: list[dict],
        assistant_content: str | None,
        tool_calls: list[dict],
        tool_results: list[dict],
    ) -> list[dict]:
        system = await self._build_system(user_id)
        history = await self._build_history_with_tools(
            messages, assistant_content, tool_calls, tool_results
        )
        return [system] + history

    async def _build_system(self, user_id: str) -> dict:
        content = SYSTEM_PROMPT
        try:
            from app.core.config import settings as s

            qdrant_client = self.qdrant
            if qdrant_client is None:
                from app.core.qdrant import get_qdrant

                qdrant_client = await get_qdrant()
                collection = getattr(s, "qdrant_memory_collection", "memory")
                qdrant_svc = self._make_qdrant_svc(qdrant_client, collection)
            else:
                qdrant_svc = self.qdrant

            from app.services.summary_service import SummaryService

            summary_svc = SummaryService(db=self.db, llm=self.llm, qdrant=qdrant_svc)
            query = ""
            if hasattr(self, "_last_user_query"):
                query = self._last_user_query
            context = await summary_svc.get_injection_context(user_id, query)

            from app.services.memory_fact import MemoryFactService

            fact_svc = MemoryFactService(self.db)
            structured = await fact_svc.get_structured_context(user_id)

            if context or structured:
                additions = []
                if context:
                    additions.append(context)
                if structured:
                    additions.append(structured)
                content += "\n" + "\n".join(additions)
                logger.info(
                    "Memory injected for user %s (narrative=%d chars, structured=%d chars)",
                    user_id,
                    len(context) if context else 0,
                    len(structured) if structured else 0,
                )
        except Exception as e:
            logger.warning("Memory injection failed (non-blocking): %s", e)

        return {"role": "system", "content": content}

    def _make_qdrant_svc(self, client, collection: str):
        from app.services.qdrant_service import QdrantService

        return QdrantService(client=client, collection=collection)

    async def _build_history(self, messages: list[dict]) -> list[dict]:
        if not messages:
            return []
        budget = HISTORY_BUDGET
        result: list[dict] = []
        total = 0
        for msg in reversed(messages):
            tokens = count_message_tokens(msg, self.model)
            if total + tokens > budget and result:
                break
            result.append(msg)
            total += tokens
        return list(reversed(result))

    async def _build_history_with_tools(
        self,
        messages: list[dict],
        assistant_content: str | None,
        tool_calls: list[dict],
        tool_results: list[dict],
    ) -> list[dict]:
        history = await self._build_history(messages)

        tool_call_msgs = self._format_tool_calls(tool_calls, assistant_content)
        tool_result_msgs = self._format_tool_results(tool_calls, tool_results)

        tool_block_tokens = count_messages_tokens(
            tool_call_msgs + tool_result_msgs, self.model
        )
        available = TOOL_RESULT_HISTORY_BUDGET - tool_block_tokens

        truncated_results = tool_result_msgs
        if available < 0:
            truncated_results = self._truncate_tool_messages(
                tool_result_msgs, TOOL_RESULT_TOKENS
            )
        elif len(tool_result_msgs) > 1:
            truncated_results = self._truncate_tool_messages(
                tool_result_msgs, available
            )

        remaining = TOOL_RESULT_HISTORY_BUDGET - count_messages_tokens(
            tool_call_msgs + truncated_results, self.model
        )
        if remaining < 0:
            tool_call_msgs = self._truncate_tool_messages(
                tool_call_msgs, TOOL_RESULT_HISTORY_BUDGET // 2
            )
            truncated_results = self._truncate_tool_messages(
                truncated_results, TOOL_RESULT_HISTORY_BUDGET // 2
            )

        trimmed_history = self._trim_history_to_budget(
            history, TOOL_RESULT_HISTORY_BUDGET
        )

        return trimmed_history + tool_call_msgs + truncated_results

    def _trim_history_to_budget(
        self, history: list[dict], budget: int
    ) -> list[dict]:
        result: list[dict] = []
        total = 0
        for msg in reversed(history):
            tokens = count_message_tokens(msg, self.model)
            if total + tokens > budget and result:
                break
            result.append(msg)
            total += tokens
        return list(reversed(result))

    @staticmethod
    def _normalize_tool_call(tc: dict | object, index: int) -> dict:
        """Normalize a tool call from dict or OpenAI object to a plain dict."""
        if isinstance(tc, dict):
            return tc
        if hasattr(tc, "model_dump"):
            return tc.model_dump()
        if hasattr(tc, "__dict__"):
            return dict(tc.__dict__)
        return {"id": getattr(tc, "id", f"call_{index}"), "function": getattr(tc, "function", {})}

    def _format_tool_calls(
        self, tool_calls: list[dict], content: str | None
    ) -> list[dict]:
        if not tool_calls:
            return []
        stubs = []
        for i, tc in enumerate(tool_calls):
            normalized = self._normalize_tool_call(tc, i)
            fn = normalized.get("function", {})
            if isinstance(fn, dict):
                fn_name = fn.get("name", "")
                fn_args = fn.get("arguments", "{}")
            else:
                fn_name = getattr(fn, "name", "")
                fn_args = getattr(fn, "arguments", "{}")
            stubs.append({
                "id": normalized.get("id", f"call_{i}"),
                "type": "function",
                "function": {"name": fn_name, "arguments": fn_args},
            })
        return [
            {
                "role": "assistant",
                "content": content,
                "tool_calls": stubs,
            }
        ]

    def _format_tool_results(
        self, tool_calls: list[dict], tool_results: list[dict]
    ) -> list[dict]:
        msgs = []
        for i, tr in enumerate(tool_results):
            tool_call_id = None
            if i < len(tool_calls):
                tc = tool_calls[i]
                if isinstance(tc, dict):
                    tool_call_id = tc.get("id", f"call_{i}")
            content: str
            if "error" in tr:
                content = json.dumps({"error": tr["error"]}, ensure_ascii=False)
            else:
                content = json.dumps(tr.get("result", tr), ensure_ascii=False, default=str)
            msgs.append({
                "role": "tool",
                "tool_call_id": tool_call_id or f"call_{i}",
                "content": content,
            })
        return msgs

    def _truncate_tool_messages(self, msgs: list[dict], budget: int) -> list[dict]:
        total = count_messages_tokens(msgs, self.model)
        if total <= budget:
            return msgs
        result: list[dict] = []
        count = 0
        for msg in reversed(msgs):
            tokens = count_message_tokens(msg, self.model)
            if count + tokens > budget and result:
                break
            result.append(msg)
            count += tokens
        return list(reversed(result))
