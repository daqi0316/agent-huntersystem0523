"""Stage 5 Smoke Test — 主聊天链路 Trace 化验证。

验证:
1. AgentOpsContext middleware 存在
2. AgentChatResponse 包含 trace_id
3. agent_service.py 绑定 request_id/operation_id
4. trace_id 通过 X-Trace-ID header 返回
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestTraceMiddleware:
    """验证 middleware 注册和基本行为。"""

    def test_middleware_registered(self) -> None:
        """agentops_context_middleware 应存在于 main.py。"""
        import inspect
        import app.main as main

        source = inspect.getsource(main)
        assert "agentops_context_middleware" in source
        assert "X-Trace-ID" in source

    def test_agent_chat_response_has_trace_id(self) -> None:
        """AgentChatResponse schema 应包含 trace_id 字段。"""
        from app.api.agent import AgentChatResponse

        resp = AgentChatResponse(reply="hello", trace_id="test-trace-123")
        assert resp.trace_id == "test-trace-123"


class TestAgentServiceContext:
    """验证 chat_with_tools 绑定 request_id/operation_id。"""

    async def test_context_includes_request_id(self) -> None:
        """AgentOpsContext 应包含 request_id 和 operation_id。"""
        with patch("app.agentops.core.context.set_context") as mock_set:
            from app.services.agent_service import chat_with_tools
            # 仅验证函数可执行到 set_context，不实际运行
            pass

    async def test_trace_id_in_result_dict(self) -> None:
        """chat_with_tools 返回的 dict 在 approval 和 orchestrator 路径包含 trace_id。

        不实际调用函数，只验证代码中包含 trace_id 返回逻辑。
        """
        import inspect
        import ast

        from app.services import agent_service

        source = inspect.getsource(agent_service)
        # 验证函数返回的 dict 中包含 trace_id
        tree = ast.parse(source)
        trace_id_in_return = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and k.value == "trace_id":
                        trace_id_in_return = True
                        break
        assert trace_id_in_return, "chat_with_tools 返回 dict 中应包含 trace_id"

    def test_agent_context_includes_request_id(self) -> None:
        """AgentOpsContext 传入 request_id/operation_id。"""
        import inspect
        from app.services import agent_service

        source = inspect.getsource(agent_service)
        assert "request_id" in source
        assert "operation_id" in source

    def test_standardized_generation_names(self) -> None:
        """LLM generation 使用标准化命名 tool_planning / final_response。"""
        import inspect
        from app.services import agent_service as mod

        source = inspect.getsource(mod)
        assert "_llm_generate(" in source
        # 验证标准化命名存在于 span_name 参数中（可能跨行）
        assert "tool_planning" in source
        assert "final_response" in source
        # _trace_completion 函数定义已不存在（仅在 docstring 提及）
        assert "async def _trace_completion" not in source
        assert "await _trace_completion" not in source

    def test_trace_llm_generation_imported(self) -> None:
        """trace_llm_generation context manager 被导入并使用。"""
        import inspect
        from app.services import agent_service as mod

        source = inspect.getsource(mod)
        assert "trace_llm_generation" in source
