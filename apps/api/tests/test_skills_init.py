from __future__ import annotations

from unittest.mock import Mock, patch

import app.skills
from app.skills.base import Skill


class FakeSkill(Skill):
    @property
    def name(self):
        return "test_skill"

    @property
    def description(self):
        return "test desc"

    def get_tools(self):
        return [{"function": {"name": "test_tool"}}]

    def get_handlers(self):
        return {"test_tool": lambda: None}


class TestDiscoverSkills:
    @patch("app.skills.pkgutil.iter_modules")
    @patch("app.skills.importlib.import_module")
    def test_discovers_skills(self, mock_import, mock_iter):
        mock_iter.return_value = [
            Mock(name="__init__"),
            Mock(name="base"),
            Mock(name="test_skill"),
        ]
        fake_mod = Mock()
        fake_mod.skill = FakeSkill()
        mock_import.return_value = fake_mod

        app.skills._discovered = None
        result = app.skills.discover_skills()

        assert "test_skill" in result

    @patch("app.skills.pkgutil.iter_modules")
    def test_skips_init_and_base(self, mock_iter):
        mock_iter.return_value = [Mock(name="__init__")]
        app.skills._discovered = None
        result = app.skills.discover_skills()
        assert result == {}

    @patch("app.skills.pkgutil.iter_modules")
    @patch("app.skills.importlib.import_module")
    def test_skips_module_without_skill(self, mock_import, mock_iter):
        mock_iter.return_value = [Mock(name="noskill")]
        fake_mod = Mock()
        fake_mod.skill = None
        mock_import.return_value = fake_mod
        app.skills._discovered = None
        result = app.skills.discover_skills()
        assert result == {}

    @patch("app.skills.pkgutil.iter_modules")
    @patch("app.skills.importlib.import_module")
    def test_handles_import_error(self, mock_import, mock_iter):
        mock_iter.return_value = [Mock(name="broken")]
        mock_import.side_effect = ImportError("broken module")
        app.skills._discovered = None
        result = app.skills.discover_skills()
        assert result == {}

    def test_caches_result(self):
        app.skills._discovered = {"cached": FakeSkill()}
        result1 = app.skills.discover_skills()
        result2 = app.skills.discover_skills()
        assert result1 is result2
        assert "cached" in result1


class TestAllTools:
    @patch("app.skills.discover_skills")
    def test_merges_tools(self, mock_discover):
        s1 = FakeSkill()
        mock_discover.return_value = {"test": s1}
        result = app.skills.all_tools()
        assert result == [{"function": {"name": "test_tool"}}]


class TestAllHandlers:
    @patch("app.skills.discover_skills")
    def test_merges_handlers(self, mock_discover):
        s1 = FakeSkill()
        mock_discover.return_value = {"test": s1}
        result = app.skills.all_handlers()
        assert "test_tool" in result
