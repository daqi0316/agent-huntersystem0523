"""Tests for app.llm.router — ModelRouter + ProviderConfigCache."""

from unittest.mock import AsyncMock, patch

import pytest

from app.llm.router.cache import ProviderConfig, ProviderConfigCache
from app.llm.provider.base import ErrorCategory, ProviderError
from app.llm.router.router import (
    AllProvidersFailed,
    EmbeddingNotAvailable,
    ModelRouter,
    get_model_router,
    reset_model_router,
)


class TestProviderConfig:
    def test_dataclass_fields(self):
        cfg = ProviderConfig(
            id="1", name="Test", provider_type="openai_compat",
            base_url="http://test", model_name="test-model",
            api_key="sk-test", timeout_seconds=30, max_retries=2,
            capabilities={"chat": True}, is_primary=True, is_fallback=False, is_active=True,
        )
        assert cfg.name == "Test"
        assert cfg.provider_type == "openai_compat"
        assert cfg.is_primary
        assert not cfg.is_fallback
        assert cfg.capabilities["chat"]


class TestProviderConfigCache:
    @pytest.fixture
    def cache(self):
        return ProviderConfigCache()

    def test_initial_state(self, cache):
        assert cache._primary is None
        assert cache._fallback is None

    def test_invalidate(self, cache):
        cache._updated_at = 12345.0
        cache.invalidate()
        assert cache._updated_at == 0.0


class TestModelRouter:
    @pytest.fixture
    def router(self):
        reset_model_router()
        return get_model_router()

    def test_singleton(self, router):
        assert get_model_router() is router

    def test_invalidate_cache(self, router):
        router.invalidate_cache()
        # After invalidate, cache TTL is 0 so next get() will reload from DB
        assert router._cache._updated_at == 0.0

    @pytest.mark.asyncio
    async def test_embed_not_available(self, router):
        """No models configured → EmbeddingNotAvailable."""
        # Ensure cache is empty
        router._cache._primary = None
        router._cache._fallback = None
        router._cache._updated_at = 0.0

        with patch.object(router._cache, "_reload", return_value=(None, None)):
            with pytest.raises(EmbeddingNotAvailable):
                await router.embed(["test text"])

    def test_all_providers_failed_exception(self):
        err = AllProvidersFailed([
            ("primary", ProviderError(ErrorCategory.SERVER_ERROR, "fail")),
        ])
        assert "primary" in str(err)
        assert "fail" in str(err)

    @pytest.mark.asyncio
    async def test_embed_find_embed_model_success(self, router):
        """Find embed model when primary doesn't support it."""
        primary = ProviderConfig(
            id="1", name="NoEmbed", provider_type="openai_compat",
            base_url="http://x", model_name="no-embed",
            api_key=None, timeout_seconds=30, max_retries=2,
            capabilities={"chat": True, "embedding": False},
            is_primary=True, is_fallback=False, is_active=True,
        )
        router._cache._primary = primary
        router._cache._fallback = None
        router._cache._updated_at = float("inf")

        # Mock _find_embed_model to return a simple mock
        mock_cfg = ProviderConfig(
            id="2", name="EmbedModel", provider_type="openai_compat",
            base_url="http://y", model_name="embed-model",
            api_key=None, timeout_seconds=30, max_retries=2,
            capabilities={"chat": True, "embedding": True},
            is_primary=False, is_fallback=False, is_active=True,
        )
        router._find_embed_model = AsyncMock(return_value=mock_cfg)

        # Mock provider pool
        mock_provider = AsyncMock()
        mock_provider.embed.return_value = [[0.1, 0.2, 0.3]]
        mock_get = AsyncMock(return_value=mock_provider)
        router._pool.get_provider = mock_get

        result = await router.embed(["test"])
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]
