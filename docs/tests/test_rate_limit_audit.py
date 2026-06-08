"""F20: 验 rate-limit-audit.md 文档完整性 (A1 已有 145 行 + F20 补充 §11).

不依赖真 backend, 纯文本 grep:
- 文档存在
- 覆盖 A1 3-key (org/user/IP 限流)
- 覆盖 v0.7 鉴权 (per-host pre-shared key)
- v0.8 60 并发明确标 "未找到" (审计负向发现)
- 引用 rate_limit_check_total 指标
- 含 admin SOP
"""

from __future__ import annotations

from pathlib import Path

DOC_PATH = Path(__file__).resolve().parent.parent / "rate-limit-audit.md"


def test_doc_exists() -> None:
    assert DOC_PATH.exists(), f"{DOC_PATH} not found"
    content = DOC_PATH.read_text()
    assert len(content) > 1000, f"doc too short: {len(content)} chars"


def test_a1_3key_rate_limit() -> None:
    content = DOC_PATH.read_text()
    for key in ("org", "user", "ip"):
        assert f"key '{key}'" in content.lower() or f"`{key}`" in content, f"missing A1 key {key!r}"
    for limit in ("100 req/min", "60 req/min", "30 req/min"):
        assert limit in content, f"missing A1 limit {limit!r}"


def test_v07_skill_cli_auth() -> None:
    content = DOC_PATH.read_text()
    assert "v0.7" in content
    assert "skill_cli" in content
    assert "pre-shared" in content
    assert "per-host" in content


def test_v08_60_concurrent_not_found() -> None:
    """F20 关键: 明确标 v0.8 60 并发 '未找到', 防止 followups 误记继续."""
    content = DOC_PATH.read_text()
    assert "60 并发" in content or "60 concurr" in content.lower()
    assert "未找到" in content, "must explicitly note v0.8 60 并发 not found"
    assert "followups" in content or "F20" in content


def test_metrics_and_sop() -> None:
    content = DOC_PATH.read_text()
    assert "rate_limit_check_total" in content
    assert "admin_reset" in content or "/admin/rate-limit" in content
    assert "SOP" in content or "运维" in content


def test_momus_3_套_对比_table() -> None:
    """F20 §11.3: 3 套策略对比表 (v0.7 鉴权 + A1 限流 + v0.8 未找到)."""
    content = DOC_PATH.read_text()
    assert "v0.7 鉴权" in content
    assert "A1 限流" in content
    assert "未找到" in content


if __name__ == "__main__":
    test_doc_exists()
    test_a1_3key_rate_limit()
    test_v07_skill_cli_auth()
    test_v08_60_concurrent_not_found()
    test_metrics_and_sop()
    test_momus_3_套_对比_table()
    print("6 passed")
