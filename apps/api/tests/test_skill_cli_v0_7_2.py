"""v0.7.2: skill_cli 鉴权 + 审计 log 测试."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2]
SKILL_CLI = API_ROOT / "app" / "scripts" / "skill_cli.py"


def _run_cli(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "app.scripts.skill_cli", *args],
        capture_output=True,
        text=True,
        cwd=str(API_ROOT),
        env=env,
        timeout=30,
    )


def _make_admin_key(tmp_path, monkeypatch) -> Path:
    """建临时 admin key 文件 + monkeypatch Path.home()."""
    key_file = tmp_path / ".skill_admin_key"
    key_file.write_text("test-admin-secret-12345")
    key_file.chmod(0o600)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return key_file


def test_cli_enable_audit_log_persists_to_jsonl(tmp_path, monkeypatch):
    """enable 后审计 log 写入 .omo/skill_cli_audit.jsonl, 含 6 字段."""
    _make_admin_key(tmp_path, monkeypatch)

    audit_path = API_ROOT / ".omo" / "skill_cli_audit.jsonl"
    if audit_path.exists():
        audit_path.unlink()
    monkeypatch.setattr("app.scripts.skill_cli._AUDIT_PATH", audit_path)

    result = _run_cli("list", "--filter", "enabled")
    skills = json.loads(result.stdout)["skills"]
    if not skills:
        pytest.skip("no enabled skills in test env")
    name = skills[0]["name"]

    result = _run_cli("enable", name)
    assert result.returncode == 0

    assert audit_path.exists()
    lines = audit_path.read_text().strip().splitlines()
    assert len(lines) >= 1
    last = json.loads(lines[-1])
    assert last["action"] == "enable"
    assert last["skill_name"] == name
    assert last["before"] is True  # was enabled, 仍然 enabled (idempotent)
    assert last["after"] is True
    assert "ts" in last and "user" in last


def test_cli_disable_audit_log_records_before_false(tmp_path, monkeypatch):
    """disable 审计 log 记录 before=False, after=False (still disabled after 2nd call)."""
    _make_admin_key(tmp_path, monkeypatch)

    audit_path = API_ROOT / ".omo" / "skill_cli_audit.jsonl"
    if audit_path.exists():
        audit_path.unlink()
    monkeypatch.setattr("app.scripts.skill_cli._AUDIT_PATH", audit_path)

    result = _run_cli("list", "--filter", "enabled")
    skills = json.loads(result.stdout)["skills"]
    if not skills:
        pytest.skip("no enabled skills in test env")
    name = skills[0]["name"]

    # disable
    result = _run_cli("disable", name)
    assert result.returncode == 0

    # audit log
    lines = audit_path.read_text().strip().splitlines()
    last = json.loads(lines[-1])
    assert last["action"] == "disable"
    assert last["skill_name"] == name
    assert last["before"] is True  # 改前是 enabled
    assert last["after"] is False

    # 还原 (re-enable)
    result = _run_cli("enable", name)


def test_cli_require_admin_exits_when_no_key_file(tmp_path):
    """SKILL_CLI_REQUIRE_ADMIN=1 但无 ~/.skill_admin_key 时 CLI 拒收 (exit 非 0)."""
    # subprocess 继承 HOME env, Path.home() 读 $HOME → tmp_path (无 key 文件)
    result = _run_cli(
        "list",
        env_extra={
            "SKILL_CLI_REQUIRE_ADMIN": "1",
            "HOME": str(tmp_path),
        },
    )

    assert result.returncode != 0
    assert "admin key file not found" in result.stderr or "admin key file not found" in result.stdout


def test_cli_require_admin_exits_on_wrong_key(tmp_path):
    """SKILL_CLI_REQUIRE_ADMIN=1 + 错 key 时 CLI 拒收 (exit 非 0)."""
    key_file = tmp_path / ".skill_admin_key"
    key_file.write_text("correct-key-abc123")

    result = _run_cli(
        "list",
        env_extra={
            "SKILL_CLI_REQUIRE_ADMIN": "1",
            "SKILL_CLI_ADMIN_KEY": "wrong-key-xyz",
            "HOME": str(tmp_path),
        },
    )

    assert result.returncode != 0
    assert "invalid admin key" in result.stderr or "invalid admin key" in result.stdout
