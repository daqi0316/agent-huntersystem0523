"""test_ephemeral.py — Ephemeral 临时覆盖层测试。"""

import os
from unittest.mock import patch

import pytest

from app.agents.prompts.ephemeral import (
    ephemeral_override,
    get_ephemeral_text,
    clear_ephemeral,
    is_ephemeral_enabled,
)
from app.agents.prompts.prompt_builder import assemble, PromptBundle


class TestEphemeralModule:
    """ephemeral.py 核心函数测试。"""

    def test_ephemeral_default_disabled(self):
        assert is_ephemeral_enabled() is False

    def test_ephemeral_set_and_get(self):
        ephemeral_override("# debug prompt")
        assert get_ephemeral_text() == "# debug prompt"
        clear_ephemeral()
        assert get_ephemeral_text() == ""

    def test_ephemeral_clears_on_clear(self):
        ephemeral_override("temp content")
        clear_ephemeral()
        assert get_ephemeral_text() == ""

    def test_ephemeral_empty_string_clears(self):
        ephemeral_override("# something")
        ephemeral_override("")
        assert get_ephemeral_text() == ""

    def test_thread_isolation(self):
        import threading
        results = {}

        def set_in_thread():
            ephemeral_override("thread-a-content")
            results[threading.current_thread().name] = get_ephemeral_text()

        t = threading.Thread(target=set_in_thread, name="worker")
        t.start()
        t.join()

        assert get_ephemeral_text() == ""
        assert results["worker"] == "thread-a-content"


class TestAssembleEphemeral:
    """assemble() 对 ephemeral 层的处理。"""

    def _make_bundle(self, **kwargs) -> PromptBundle:
        defaults = dict(
            soul="SOUL", memory="", user="", project="", skills_index="",
            agent="", safety="", env="", ephemeral=""
        )
        defaults.update(kwargs)
        return PromptBundle(**defaults)

    def test_disabled_flag_ignores_thread_local(self):
        bundle = self._make_bundle(ephemeral="# bundle-ephemeral")
        with patch.dict(os.environ, {"EPHEMERAL_ENABLED": "false"}):
            ephemeral_override("# thread-override")
            result = assemble(bundle)
        assert "# thread-override" not in result
        assert "# bundle-ephemeral" in result
        clear_ephemeral()

    def test_enabled_thread_override_wins_over_bundle(self):
        bundle = self._make_bundle(ephemeral="# bundle-ephemeral")
        with patch.dict(os.environ, {"EPHEMERAL_ENABLED": "true"}):
            ephemeral_override("# thread-override")
            result = assemble(bundle)
        assert "# thread-override" in result
        assert "# bundle-ephemeral" not in result
        clear_ephemeral()

    def test_enabled_no_thread_override_uses_bundle(self):
        bundle = self._make_bundle(ephemeral="# from-bundle")
        with patch.dict(os.environ, {"EPHEMERAL_ENABLED": "true"}):
            clear_ephemeral()
            result = assemble(bundle)
        assert "# from-bundle" in result

    def test_enabled_empty_thread_local_skips_ephemeral(self):
        bundle = self._make_bundle(ephemeral="")
        with patch.dict(os.environ, {"EPHEMERAL_ENABLED": "true"}):
            clear_ephemeral()
            result = assemble(bundle)
        assert result == "SOUL"


class TestEphemeralEnabledEnvFlag:

    def test_env_flag_true_enables(self, monkeypatch):
        monkeypatch.setenv("EPHEMERAL_ENABLED", "true")
        import importlib
        import app.agents.prompts.ephemeral as ep
        importlib.reload(ep)
        assert ep.is_ephemeral_enabled() is True
        monkeypatch.setenv("EPHEMERAL_ENABLED", "false")
        importlib.reload(ep)

    def test_env_flag_false_disables(self, monkeypatch):
        monkeypatch.setenv("EPHEMERAL_ENABLED", "false")
        import importlib
        import app.agents.prompts.ephemeral as ep
        importlib.reload(ep)
        assert ep.is_ephemeral_enabled() is False
