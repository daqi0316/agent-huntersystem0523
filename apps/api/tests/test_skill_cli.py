"""v0.7.1 skill_cli CLI 测试."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2]
SKILL_CLI = API_ROOT / "app" / "scripts" / "skill_cli.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """调 `python -m app.scripts.skill_cli <args>`."""
    return subprocess.run(
        [sys.executable, "-m", "app.scripts.skill_cli", *args],
        capture_output=True,
        text=True,
        cwd=str(API_ROOT),
        timeout=30,
    )


def test_cli_list_returns_skills_json():
    """skill_cli list 返 JSON 含 skills 列表."""
    result = _run_cli("list")

    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert "skills" in payload
    assert isinstance(payload["skills"], list)
    assert payload["count"] == len(payload["skills"])


def test_cli_list_filter_enabled_only():
    """skill_cli list --filter enabled 只返 enabled."""
    result = _run_cli("list", "--filter", "enabled")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    for skill in payload["skills"]:
        assert skill["enabled"] is True


def test_cli_get_existing_skill():
    """skill_cli get <name> 返 skill 详情."""
    result = _run_cli("list", "--filter", "enabled")
    skills = json.loads(result.stdout)["skills"]
    if not skills:
        pytest.skip("no enabled skills in test env")

    name = skills[0]["name"]
    result = _run_cli("get", name)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["name"] == name
    assert "tools" in payload


def test_cli_get_nonexistent_skill_exits_nonzero():
    """skill_cli get <不存在> 返 NOT_FOUND + exit 1."""
    result = _run_cli("get", "nonexistent-skill-xyz-9876")

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert payload["code"] == "NOT_FOUND"


def test_cli_enable_disable_roundtrip():
    """skill_cli enable → disable 同一 skill 闭环 (state.json 持久化)."""
    result = _run_cli("list", "--filter", "enabled")
    skills = json.loads(result.stdout)["skills"]
    if not skills:
        pytest.skip("no enabled skills in test env")

    name = skills[0]["name"]

    # disable
    result = _run_cli("disable", name)
    assert result.returncode == 0, f"disable stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["enabled"] is False

    # 立即再 list, 该 skill 应在 disabled 里
    result = _run_cli("list", "--filter", "disabled")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert any(s["name"] == name for s in payload["skills"])

    # enable (还原)
    result = _run_cli("enable", name)
    assert result.returncode == 0, f"enable stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["enabled"] is True


def test_cli_help_exits_zero():
    """skill_cli --help 返 usage."""
    result = _run_cli("--help")

    assert result.returncode == 0
    assert "list" in result.stdout
    assert "enable" in result.stdout
    assert "disable" in result.stdout
