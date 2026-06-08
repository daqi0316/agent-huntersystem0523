"""T 测: dedup + reorder §8/§9 (前次 F retrofit 跑过可能产生重复 §9)."""
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

if 'retrofit_ship_reports' in sys.modules:
    del sys.modules['retrofit_ship_reports']
from retrofit_ship_reports import retrofit_one


def test_retrofit_ship_reports_dedup_9():
    """T 测: dedup §9 (F retrofit 跑过产生 2 §9 → 合并 1)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "followup-test-ship-report.md"
        p.write_text(
            "# T\n\n"
            "## 1. 概览\n\n✅ ✅ ✅\n\n"
            "## 2. 背景\n\nb\n\n"
            "## 3. 修法\n\nm\n\n"
            "## 4. 测试\n\n测试策略: mock\n\n"
            "## 5. 退出门槛\n\n5 强约束: PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死\n\n"
            "## 6. 未在\n\nx\n\n"
            "## 7. 后续\n\n(F retrofit 标)\n\n"
            "## 9. 引用\n\n(F retrofit 保留原 §7 引用 内容):\nold refs\n\n"
            "## 8. 回滚\n\nrollback: git revert\n\n"
            "## 9. 引用\n\n- Refs: [new](http://new)\n",
            encoding="utf-8",
        )
        changed, msg = retrofit_one(p)
        new_content = p.read_text(encoding="utf-8")
        import re
        s9_count = len(list(re.finditer(r"^## 9\. ", new_content, re.MULTILINE)))
        assert s9_count == 1, f"应 1 个 §9, 实际 {s9_count}"
        # 验证 §7 < §8 < §9 顺序
        s7 = re.search(r"^## 7\. ", new_content, re.MULTILINE).start()
        s8 = re.search(r"^## 8\. ", new_content, re.MULTILINE).start()
        s9 = re.search(r"^## 9\. ", new_content, re.MULTILINE).start()
        assert s7 < s8 < s9, f"§7({s7}) < §8({s8}) < §9({s9}) 顺序错"
        # 验证 old + new 内容都保留
        assert "old refs" in new_content, "应保留旧 §9 内容"
        assert "[new](http://new)" in new_content, "应保留新 §9 内容"
    print(f"✅ T 测: dedup §9 (2→1) + reorder §7 < §8 < §9")


def test_retrofit_ship_reports_idempotent_after_dedup():
    """T 测: dedup 后再跑 idempotency (无变化)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "followup-test-ship-report.md"
        p.write_text(
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
        original = p.read_text(encoding="utf-8")
        changed, msg = retrofit_one(p)
        assert not changed, f"已合规应 idempotency: {msg}"
    print("✅ T 测: dedup 后 idempotency")


if __name__ == "__main__":
    test_retrofit_ship_reports_dedup_9()
    test_retrofit_ship_reports_idempotent_after_dedup()
    print("\n=== 2/2 测过 ===")
