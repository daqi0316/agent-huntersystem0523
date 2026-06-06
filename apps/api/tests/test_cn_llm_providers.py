"""P6-8 跨 phase: 国内 LLM provider 测试。"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestProviderRegistry:
    def test_supported_providers(self):
        from app.llm.cn_providers import CN_PROVIDERS, list_supported_providers
        assert set(CN_PROVIDERS.keys()) == {"qwen", "deepseek", "zhipu"}
        listed = list_supported_providers()
        names = {p["name"] for p in listed}
        assert names == {"qwen", "deepseek", "zhipu"}
        for p in listed:
            assert p["openai_compat"] is True
            assert p["base_url"].startswith("https://")
            assert p["env_key"].endswith("_API_KEY")

    def test_default_models(self):
        from app.llm.cn_providers import CN_PROVIDERS
        assert CN_PROVIDERS["qwen"].default_model == "qwen-plus"
        assert CN_PROVIDERS["deepseek"].default_model == "deepseek-chat"
        assert CN_PROVIDERS["zhipu"].default_model == "glm-4-plus"


class TestFactory:
    def test_factory_qwen(self):
        from app.llm.cn_providers import QwenClient, get_cn_llm_client
        os.environ["QWEN_API_KEY"] = "test-qwen-key"
        with patch("app.llm.cn_providers.AsyncOpenAI") as mock_openai:
            client = get_cn_llm_client("qwen")
        assert isinstance(client, QwenClient)
        mock_openai.assert_called_once()
        kw = mock_openai.call_args.kwargs
        assert kw["api_key"] == "test-qwen-key"
        assert "dashscope.aliyuncs.com" in kw["base_url"]

    def test_factory_deepseek(self):
        from app.llm.cn_providers import DeepSeekClient, get_cn_llm_client
        os.environ["DEEPSEEK_API_KEY"] = "test-deepseek-key"
        with patch("app.llm.cn_providers.AsyncOpenAI") as mock_openai:
            client = get_cn_llm_client("deepseek")
        assert isinstance(client, DeepSeekClient)
        assert "deepseek.com" in mock_openai.call_args.kwargs["base_url"]

    def test_factory_zhipu(self):
        from app.llm.cn_providers import ZhipuClient, get_cn_llm_client
        os.environ["ZHIPU_API_KEY"] = "test-zhipu-key"
        with patch("app.llm.cn_providers.AsyncOpenAI") as mock_openai:
            client = get_cn_llm_client("zhipu")
        assert isinstance(client, ZhipuClient)
        assert "bigmodel.cn" in mock_openai.call_args.kwargs["base_url"]

    def test_factory_unknown(self):
        from app.llm.cn_providers import get_cn_llm_client
        with pytest.raises(ValueError, match="Unknown CN LLM provider"):
            get_cn_llm_client("openai")


class TestMainFactory:
    def test_main_factory_routes_to_cn(self):
        from app.llm import get_llm_client
        with patch("app.llm.get_cn_llm_client") as mock_get:
            mock_get.return_value = MagicMock()
            with patch("app.llm.settings") as mock_settings:
                mock_settings.llm_provider = "deepseek"
                client = get_llm_client()
        assert mock_get.called
        assert mock_get.call_args.args[0] == "deepseek"

    def test_main_factory_unknown_raises(self):
        from app.llm import get_llm_client
        with patch("app.llm.settings") as mock_settings:
            mock_settings.llm_provider = "gpt-4"
            with pytest.raises(ValueError, match="Unknown LLM provider"):
                get_llm_client()


class TestChatCall:
    def test_qwen_chat_invokes_openai(self):
        from app.llm.cn_providers import QwenClient
        from app.llm import cn_providers
        os.environ["QWEN_API_KEY"] = "test-key"
        with patch.object(cn_providers.settings, "llm_model", None):
            with patch("app.llm.cn_providers.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
                mock_openai.return_value = mock_client
                client = QwenClient()
                import asyncio
                result = asyncio.run(client.chat([{"role": "user", "content": "hi"}]))
        assert result is mock_response
        mock_client.chat.completions.create.assert_called_once()
        kw = mock_client.chat.completions.create.call_args.kwargs
        assert kw["model"] == "qwen-plus"
        assert kw["messages"] == [{"role": "user", "content": "hi"}]
