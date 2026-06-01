"""Tests for PostgresSaver / MemorySaver selection in orchestrator._build_checkpointer.

Verifies that:
  1. Without LANGGRAPH_PG_DSN env var → MemorySaver is used
  2. With valid LANGGRAPH_PG_DSN → PostgresSaver.from_conn_string is called
  3. PostgresSaver init failure → falls back to MemorySaver (no crash)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Reset the graph cache + clear any cached settings."""
    from app.api.orchestrator import reset_graph_cache

    reset_graph_cache()
    yield
    reset_graph_cache()


def test_memory_saver_when_dsn_unset(monkeypatch):
    """No LANGGRAPH_PG_DSN → MemorySaver fallback."""
    monkeypatch.delenv("LANGGRAPH_PG_DSN", raising=False)

    # Reload settings to pick up cleared env
    from app.core.config import Settings
    with patch.object(Settings, "model_config", {"env_file": ".env", "extra": "ignore"}):
        fresh = Settings()
    monkeypatch.setattr("app.api.orchestrator.settings", fresh)

    from app.api.orchestrator import _build_checkpointer

    saver = _build_checkpointer()
    assert isinstance(saver, MemorySaver)


def test_postgres_saver_when_dsn_set(monkeypatch):
    """Valid LANGGRAPH_PG_DSN → PostgresSaver.from_conn_string is called."""
    monkeypatch.setenv("LANGGRAPH_PG_DSN", "postgresql://user:pass@localhost:5432/db")

    fake_saver = MagicMock(name="PostgresSaver")
    fake_saver.setup = MagicMock()

    with patch("langgraph.checkpoint.postgres.PostgresSaver") as mock_cls:
        mock_cls.from_conn_string.return_value = fake_saver
        from app.core.config import Settings
        fresh = Settings()
        monkeypatch.setattr("app.api.orchestrator.settings", fresh)
        from app.api.orchestrator import _build_checkpointer

        saver = _build_checkpointer()

    mock_cls.from_conn_string.assert_called_once_with("postgresql://user:pass@localhost:5432/db")
    fake_saver.setup.assert_called_once()
    assert saver is fake_saver


def test_postgres_saver_init_failure_falls_back(monkeypatch):
    """PostgresSaver raises → log error + fall back to MemorySaver (no crash)."""
    monkeypatch.setenv("LANGGRAPH_PG_DSN", "postgresql://broken:bad@nowhere:5432/db")

    with patch("langgraph.checkpoint.postgres.PostgresSaver") as mock_cls:
        mock_cls.from_conn_string.side_effect = RuntimeError("connection refused")
        from app.core.config import Settings
        fresh = Settings()
        monkeypatch.setattr("app.api.orchestrator.settings", fresh)
        from app.api.orchestrator import _build_checkpointer

        saver = _build_checkpointer()

    assert isinstance(saver, MemorySaver)


def test_get_graph_uses_built_checkpointer(monkeypatch):
    """_get_graph() calls _build_checkpointer() exactly once (lazy + cached)."""
    from unittest.mock import MagicMock

    monkeypatch.delenv("LANGGRAPH_PG_DSN", raising=False)
    from app.core.config import Settings
    fresh = Settings()
    monkeypatch.setattr("app.api.orchestrator.settings", fresh)

    fake_saver = MemorySaver()
    with patch("app.api.orchestrator._build_checkpointer", return_value=fake_saver) as mock_build, \
         patch("app.api.orchestrator.create_orchestrator_graph") as mock_create:
        mock_graph = MagicMock()
        mock_create.return_value = mock_graph

        from app.api.orchestrator import _get_graph

        g1 = _get_graph()
        g2 = _get_graph()  # cached

    assert g1 is g2
    assert mock_build.call_count == 1
    mock_create.assert_called_once_with(checkpointer=fake_saver)
