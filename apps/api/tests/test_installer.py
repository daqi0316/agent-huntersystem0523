"""Unit tests for app/skills/installer.py — Skill auto-installer."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.skills.installer import (
    _make_init,
    _make_skill,
    _reload,
    _validate,
    install_skill,
    installed_list,
)


class TestValidate:
    def test_dangerous_patterns_detected(self):
        for pat in ["__import__", "eval(", "exec(", "os.system", "subprocess"]:
            issues = _validate(f"hello {pat} world")
            assert any(pat.replace("(", "") in i for i in issues), f"{pat} not caught"

    def test_missing_class(self):
        issues = _validate("def foo(): pass")
        assert any("缺少 class 定义" in i for i in issues)

    def test_missing_function(self):
        issues = _validate("class Foo: pass")
        assert any("缺少函数定义" in i for i in issues)

    def test_valid_code(self):
        code = "class Foo:\n    def bar(self): pass\n"
        issues = _validate(code)
        assert not issues


class TestMakeInit:
    def test_generates_init_content(self):
        content = _make_init("ip_lookup")
        assert "from app.skills.ip_lookup.skill import skill" in content
        assert '__all__ = ["skill"]' in content


class TestMakeSkill:
    SIMPLE_PARAMS = {"type": "object", "properties": {}}

    def test_contains_tool_schema(self):
        result = _make_skill(
            "test_skill",
            "A test skill",
            "do_test",
            "Does a test",
            "async def _do_test(): pass",
            self.SIMPLE_PARAMS,
        )
        assert "class _AutoSkill(Skill):" in result
        assert "'do_test': _do_test" in result
        assert "async def _do_test(): pass" in result

    def test_handler_code_embedded(self):
        handler = "async def _my_tool(param: str):\n    return {'result': param}"
        result = _make_skill("mytool", "desc", "my_tool", "tool desc", handler, self.SIMPLE_PARAMS)
        assert handler in result

    def test_with_parameters(self):
        params = {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        }
        result = _make_skill("fetcher", "fetch", "fetch_url", "fetches", "async def _fetch_url(): pass", params)
        assert '"url"' in result


class TestInstallSkill:
    @pytest.mark.asyncio
    async def test_successful_install(self, tmp_path):
        target_dir = tmp_path / "skills"
        target_dir.mkdir()
        with patch("app.skills.installer.SKILLS_DIR", target_dir):
            with patch("app.skills.installer._reload") as mock_reload:
                result = await install_skill(
                    name="ip_lookup",
                    description="Look up IP info",
                    tool_name="lookup_ip",
                    tool_description="Look up IP address information",
                    handler_code="async def _lookup_ip(ip: str): return {'ip': ip}",
                    parameters={"type": "object", "properties": {"ip": {"type": "string"}}},
                )

        assert result["success"] is True
        assert "ip_lookup" in result["path"]
        assert (target_dir / "ip_lookup" / "__init__.py").exists()
        assert (target_dir / "ip_lookup" / "skill.py").exists()
        mock_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_name(self, tmp_path):
        with patch("app.skills.installer.SKILLS_DIR", tmp_path):
            result = await install_skill(
                name="123-invalid",
                description="x", tool_name="x",
                tool_description="x", handler_code="class Foo: pass\ndef bar(): pass",
            )
        assert result["success"] is False
        assert "invalid" in result["error"]

    @pytest.mark.asyncio
    async def test_skill_already_exists(self, tmp_path):
        target_dir = tmp_path / "skills"
        (target_dir / "existing").mkdir(parents=True)
        with patch("app.skills.installer.SKILLS_DIR", target_dir):
            result = await install_skill(
                name="existing",
                description="x", tool_name="x",
                tool_description="x", handler_code="class Foo: pass\ndef bar(): pass",
            )
        assert result["success"] is False
        assert "already exists" in result["error"]

    @pytest.mark.asyncio
    async def test_validation_failure_on_dangerous_code(self, tmp_path):
        """Dangerous patterns in handler_code trigger validation failure."""
        with patch("app.skills.installer.SKILLS_DIR", tmp_path):
            result = await install_skill(
                name="badskill",
                description="x", tool_name="x",
                tool_description="x",
                handler_code="os.system('rm -rf /')",
            )
        assert result["success"] is False
        assert "validation failed" in result["error"]


class TestInstalledList:
    @pytest.mark.asyncio
    async def test_returns_skills(self):
        mock_skill = MagicMock()
        mock_skill.description = "A mock skill"
        mock_skill.get_tools.return_value = [{"function": {"name": "mock_tool"}}]

        with patch("app.skills.discover_skills", return_value={"mock": mock_skill}):
            result = await installed_list()

        assert len(result) == 1
        assert result[0]["name"] == "mock"
        assert result[0]["description"] == "A mock skill"
        assert result[0]["tools"] == ["mock_tool"]


class TestReload:
    def test_reload_called_with_fresh_import(self):
        with (
            patch("importlib.reload") as mock_reload,
            patch("importlib.import_module", return_value=MagicMock()) as mock_import,
        ):
            _reload()

        mock_reload.assert_called_once_with(mock_import.return_value)
