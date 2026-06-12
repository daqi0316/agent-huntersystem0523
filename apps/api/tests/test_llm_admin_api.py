"""Tests for app.llm.admin — API Key crypto + Admin API."""

from unittest.mock import AsyncMock, patch

import pytest

from app.llm.admin.crypto import decrypt_api_key, encrypt_api_key, mask_api_key


class TestCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        key = "sk-" + "a" * 40
        enc = encrypt_api_key(key)
        assert enc != key
        assert ":" in enc  # salt:encrypted format
        dec = decrypt_api_key(enc)
        assert dec == key

    def test_decrypt_none(self):
        assert decrypt_api_key(None) is None
        assert decrypt_api_key("") is None

    def test_decrypt_invalid(self):
        result = decrypt_api_key("not-valid-encrypted-data")
        assert result is None

    def test_mask_api_key_long(self):
        key = "sk-abc123def456ghi789"
        masked = mask_api_key(key)
        assert masked is not None
        assert "****" in masked
        assert len(masked) < len(key)
        assert masked.startswith("sk-abc")
        assert masked.endswith("789")

    def test_mask_api_key_short(self):
        key = "abcdef"
        masked = mask_api_key(key)
        assert masked == "abcd****"

    def test_mask_api_key_none(self):
        assert mask_api_key(None) is None
        assert mask_api_key("") is None

    def test_old_format_backward_compat(self):
        """Old format (no salt) should still be decryptable."""
        key = "test-key-old-format"
        # Force encrypt without salt by calling Fernet directly
        from app.llm.admin.crypto import _get_fernet
        f = _get_fernet("")
        old_format = f.encrypt(key.encode()).decode()
        dec = decrypt_api_key(old_format)
        assert dec == key


class TestAdminAPI:
    """Tests for the admin API endpoints."""

    @pytest.mark.asyncio
    async def test_list_presets(self):
        """The presets endpoint returns the correct number of models."""
        from app.llm.admin.api import PRESETS, list_presets
        result = await list_presets()
        assert "presets" in result
        assert len(result["presets"]) == 5

    def test_preset_fields(self):
        from app.llm.admin.api import PRESETS
        for preset in PRESETS:
            assert "name" in preset
            assert "provider_type" in preset
            assert "base_url" in preset
            assert "model_name" in preset
            assert "capabilities" in preset

    def test_preset_types(self):
        from app.llm.admin.api import PRESETS
        types = {p["provider_type"] for p in PRESETS}
        assert "openai_compat" in types
        assert "anthropic" in types

    @pytest.mark.asyncio
    async def test_router_has_10_routes(self):
        from app.llm.admin.api import router
        # 10 routes: GET/POST providers, PUT/DELETE provider, primary/fallback/unset,
        # test, health, presets
        assert len(router.routes) == 10
