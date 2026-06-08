"""T 测: 3 retrofit 脚本核心函数 (regex + idempotency + section 改名).

背景: F/F2/F3 retrofit (5a63512/158fbd4/2d13fa5) ship 后, 3 retrofit 脚本
缺测. 本 T 加核心函数测, 防未来 regex 改 regression.

覆盖:
- retrofit_ship_reports.py: 14 retrofit + 1 G16+G17 手动
- retrofit_mcp_v4_ship_reports.py: 22 mcp-v4-v* 14 改 / 2 真过
- retrofit_mcp_v4_titles.py: 13 章节标题 + §9 + 5 强约束
- 共同: idempotency (无变化时无写入)
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

# 加 scripts/ 到 sys.path 复用 3 retrofit 脚本
SCRIPTS = Path(__file__).parent.parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_check_ship_report_name_pattern_compat():
    """T 测 1: NAME_PATTERN 兼容 mcp-v4-v* 老 + 新 (fix-1/pr8/phase-*/momus-*)."""
    import check_ship_report
    # 新 pattern: ^mcp-v4[\\w.\\-]+|followup-
    compat = [
        "mcp-v4-v0.4-ship-report.md",
        "mcp-v4-v1.0a-ship-report.md",
        "mcp-v4-fix-1-ship-report.md",
        "mcp-v4-pr8-ship-report.md",
        "mcp-v4-phase-a-deferred-1-ship-report.md",
        "mcp-v4-momus-audit-ship-report.md",
        "mcp-v4-mcp-v4-fix-1-ship-report.md",  # double prefix (edge case)
        "followup-f12-ci-lint-integration-ship-report.md",
    ]
    for f in compat:
        assert check_ship_report.NAME_PATTERN.match(f), f"应兼容: {f}"
        assert check_ship_report.NEW_NAME_PATTERN.match(f) if f.startswith("followup-") else True
    print(f"✅ T 测 1: NAME_PATTERN 兼容 {len(compat)} 文件名")


def test_section_keywords_required():
    """T 测 2: §5/§6/§7/§8/§9 必含 G8 关键词 (退出门槛/未在/后续/回滚/引用)."""
    import check_ship_report
    expected = {
        5: "退出门槛",
        6: "未在",
        7: "后续",
        8: "回滚",
        9: "引用",
    }
    for n, kw in expected.items():
        assert check_ship_report.SECTION_KEYWORDS[n] == kw, f"§{n} 必填 '{kw}'"
    print(f"✅ T 测 2: §5-§9 必填关键词 5/5 正确")


def test_required_constraints_keys():
    """T 测 3: 5 强约束 4 substring + rollback regex 正确."""
    import check_ship_report
    assert len(check_ship_report.REQUIRED_CONSTRAINTS) == 4
    keywords = [kw for kw, _ in check_ship_report.REQUIRED_CONSTRAINTS]
    expected = ["PR ≤ 1.5d", "+30% buffer", "1 PR 必含测", "顺序锁死"]
    assert keywords == expected, f"5 强约束 4 关键词: {keywords}"
    # rollback regex 兼容 rollback/回滚
    assert check_ship_report.ROLLBACK_PATTERN.search("rollback: git revert")
    assert check_ship_report.ROLLBACK_PATTERN.search("回滚: git revert")
    assert not check_ship_report.ROLLBACK_PATTERN.search("nothing matches")
    print(f"✅ T 测 3: 5 强约束 4 关键词 + rollback regex 兼容中英文")


def test_retrofit_mcp_v4_titles_idempotency():
    """T 测 4: retrofit_mcp_v4_titles.py idempotency (无变化时无写入)."""
    from retrofit_mcp_v4_titles import retrofit_one

    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "test-ship-report.md"
        # 写一个合规 9 章节 + G8 关键词文件
        test_file.write_text(
            "# T\n\n"
            "## 1. 概览\n\n✅ KPI\n\n"
            "## 2. 背景\n\nb\n\n"
            "## 3. 修法\n\nm\n\n"
            "## 4. 测试\n\n测试策略: mock\n\n"
            "## 5. 退出门槛 — a\n\n5 强约束适用: PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死\n\n"
            "## 6. 未在 — b\n\nc\n\n"
            "## 7. 后续 — c\n\nd\n\n"
            "## 8. 回滚 — d\n\nrollback: git revert\n\n"
            "## 9. 引用 — e\n\nf\n",
            encoding="utf-8",
        )
        original = test_file.read_text(encoding="utf-8")
        changed, msg = retrofit_one(test_file)
        assert not changed, f"已合规文件应 idempotency: {msg}"
        assert test_file.read_text(encoding="utf-8") == original, "idempotency 验证: 内容未变"
    print("✅ T 测 4: retrofit_mcp_v4_titles.py idempotency (无变化无写入)")


def test_retrofit_mcp_v4_titles_adds_missing_sections():
    """T 测 5: retrofit_mcp_v4_titles.py 实际加缺 §9 + 章节标题 keyword."""
    from retrofit_mcp_v4_titles import retrofit_one

    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "test-ship-report.md"
        # 写一个缺 §9 + 章节标题错位的文件
        test_file.write_text(
            "# T\n\n"
            "## 1. 概览\n\n✅ ✅ ✅\n\n"
            "## 2. 背景\n\nb\n\n"
            "## 3. 修法\n\nm\n\n"
            "## 4. 测试\n\n测试策略: mock\n\n"
            "## 5. 关键性能数据\n\n5\n\n"
            "## 6. v0.4 启动\n\n6\n\n"
            "## 7. 已知限制\n\n7\n\n"
            "## 8. ADR 更新\n\n8\n\n",
            encoding="utf-8",
        )
        changed, msg = retrofit_one(test_file)
        assert changed, f"应改: {msg}"
        new_content = test_file.read_text(encoding="utf-8")
        # 验证 §9 加了
        assert re.search(r"^## 9\. ", new_content, re.MULTILINE), "应加 §9"
        # 验证章节标题改了 (含 keyword)
        assert "退出门槛" in new_content
        assert "未在" in new_content
        assert "后续" in new_content
        assert "回滚" in new_content
        assert "引用" in new_content
        # 验证 5 强约束 加了
        for kw in ["PR ≤ 1.5d", "+30% buffer", "1 PR 必含测", "顺序锁死"]:
            assert kw in new_content, f"5 强约束缺: {kw}"
    print("✅ T 测 5: retrofit_mcp_v4_titles.py 加 §9 + 5 keyword + 4 5 强约束")


def test_retrofit_ship_reports_idempotency():
    """T 测 6: retrofit_ship_reports.py idempotency."""
    from retrofit_ship_reports import retrofit_one

    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "followup-test-ship-report.md"
        test_file.write_text(
            "<!-- ship-report-template: g5-g8-v1 -->\n"
            "# T\n\n"
            "## 1. 概览\n\n✅ ✅ ✅\n\n"
            "## 2. 背景\n\nb\n\n"
            "## 3. 修法\n\nm\n\n"
            "## 4. 测试\n\n测试策略: mock\n\n"
            "## 5. 退出门槛 — a\n\n5 强约束: PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死\n\n"
            "## 6. 未在 — b\n\nc\n\n"
            "## 7. 后续 — c\n\n(F retrofit 标)\n\n"
            "## 8. 回滚 — d\n\nrollback: git revert\n\n"
            "## 9. 引用 — e\n\nf\n",
            encoding="utf-8",
        )
        original = test_file.read_text(encoding="utf-8")
        changed, msg = retrofit_one(test_file)
        assert not changed, f"已合规文件应 idempotency: {msg}"
        assert test_file.read_text(encoding="utf-8") == original
    print("✅ T 测 6: retrofit_ship_reports.py idempotency")


def test_retrofit_ship_reports_handles_7_section():
    """T 测 7: retrofit_ship_reports.py 修 7-section 老文件到 9-section."""
    from retrofit_ship_reports import retrofit_one

    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "followup-test-ship-report.md"
        test_file.write_text(
            "# T\n\n"
            "## 1. 概览\n\n✅ ✅ ✅\n\n"
            "## 2. 背景\n\nb\n\n"
            "## 3. 修法\n\nm\n\n"
            "## 4. 测试\n\nno test strategy\n\n"
            "## 5. 退出门槛\n\n5 强约束: PR ≤ 1.5d / Bugfix Rule / 1 PR 必含测 / H 风险 rollback / 顺序锁死\n\n"
            "## 6. 未在\n\nx\n\n"
            "## 7. 引用\n\ny\n",
            encoding="utf-8",
        )
        changed, msg = retrofit_one(test_file)
        assert changed, f"7-section 应改: {msg}"
        new_content = test_file.read_text(encoding="utf-8")
        # 验证测试策略加了
        assert "测试策略" in new_content
        # 验证 +30% buffer 加了
        assert "+30% buffer" in new_content
        # 验证 §8 §9 加了
        assert re.search(r"^## 8\. ", new_content, re.MULTILINE)
        assert re.search(r"^## 9\. ", new_content, re.MULTILINE)
        # 验证 §7 改了
        m = re.search(r"^## 7\. (.+?)$", new_content, re.MULTILINE)
        assert m and "后续" in m.group(1)
    print("✅ T 测 7: retrofit_ship_reports.py 7-section → 9-section")


def test_retrofit_mcp_v4_ship_reports_idempotency():
    """T 测 8: retrofit_mcp_v4_ship_reports.py idempotency."""
    from retrofit_mcp_v4_ship_reports import retrofit_one

    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "mcp-v4-test-ship-report.md"
        test_file.write_text(
            "# T\n\n"
            "## 1. 概览\n\n✅ ✅ ✅\n\n"
            "## 2. 背景\n\nb\n\n"
            "## 3. 修法\n\nm\n\n"
            "## 4. 测试\n\n测试策略: mock\n\n"
            "## 5. 退出门槛 — a\n\n5 强约束: PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死\n\n"
            "## 6. 未在 — b\n\nc\n\n"
            "## 7. 后续 — c\n\nd\n\n"
            "## 8. 回滚 — d\n\nrollback: git revert\n\n"
            "## 9. 引用 — e\n\nf\n",
            encoding="utf-8",
        )
        original = test_file.read_text(encoding="utf-8")
        changed, msg = retrofit_one(test_file)
        assert not changed, f"已合规文件应 idempotency: {msg}"
    print("✅ T 测 8: retrofit_mcp_v4_ship_reports.py idempotency")
