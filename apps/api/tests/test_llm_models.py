"""Tests for app.llm.models — LlmProvider ORM model."""

import pytest

from app.llm.models.llm_provider import LlmProvider, LlmProviderType


class TestLlmProviderType:
    def test_enum_values(self):
        assert LlmProviderType.OPENAI_COMPAT.value == "openai_compat"
        assert LlmProviderType.ANTHROPIC.value == "anthropic"

    def test_enum_members(self):
        assert len(LlmProviderType) == 2


class TestLlmProviderModel:
    def test_tablename(self):
        assert LlmProvider.__tablename__ == "llm_providers"

    def test_has_required_fields(self):
        """Verify the model has all planned fields."""
        columns = {c.name for c in LlmProvider.__table__.columns}
        required = {
            "id", "name", "provider_type", "base_url", "model_name",
            "capabilities", "is_primary", "is_fallback", "is_active",
            "timeout_seconds", "max_retries", "sort_order",
            "created_at", "updated_at",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_optional_fields(self):
        columns = {c.name for c in LlmProvider.__table__.columns}
        optional = {"api_key_enc", "key_salt", "key_updated_at", "notes"}
        assert optional.issubset(columns), f"Missing optional columns: {optional - columns}"

    def test_check_constraint_exists(self):
        """Verify the NOT (is_primary AND is_fallback) constraint."""
        constraints = [c for c in LlmProvider.__table__.constraints]
        constraint_names = [c.name for c in constraints if c.name]
        assert "ck_llm_providers_not_both_primary_fallback" in constraint_names

    def test_unique_indexes(self):
        """Verify primary/fallback unique partial indexes."""
        indexes = {idx.name: idx for idx in LlmProvider.__table__.indexes}
        assert "idx_llm_providers_single_primary" in indexes
        assert "idx_llm_providers_single_fallback" in indexes
        assert "idx_llm_providers_active" in indexes

    def test_default_timeout(self):
        col = LlmProvider.__table__.columns["timeout_seconds"]
        assert col.default is not None
        assert col.default.arg == 30

    def test_default_retries(self):
        col = LlmProvider.__table__.columns["max_retries"]
        assert col.default is not None
        assert col.default.arg == 2

    def test_capabilities_jsonb(self):
        from sqlalchemy.dialects.postgresql import JSONB
        col = LlmProvider.__table__.columns["capabilities"]
        assert isinstance(col.type, JSONB)

    def test_repr(self):
        """String representation."""
        provider = LlmProvider(
            name="Test Model",
            provider_type="openai_compat",
            is_primary=True,
            is_fallback=False,
        )
        r = repr(provider)
        assert "Test Model" in r
        assert "openai_compat" in r
        assert "primary=True" in r
