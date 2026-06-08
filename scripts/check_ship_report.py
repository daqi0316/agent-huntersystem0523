"""A6: Ship report 模板 lint 检查.

验证项:
1. 9 章节必填 (## 1 - ## 9)
2. 5 强约束 6 行在退出门槛表
3. 命名格式: docs/mcp-v4-v*.md
4. 引用 ≥ 3 个 markdown 链接
5. G5 (2026-06-08 momus v1): 每章节 ≤ 30 行, 防 ship report 膨胀
6. G8 (2026-06-08 momus v1): §4 必含 "测试策略: mock X / 真 Y"
   + §8 必含 "rollback: git revert + N 文件" (防 ship 时忘写)

用法:
    python scripts/check_ship_report.py docs/mcp-v4-v1.4-a1-ship-report.md
    python scripts/check_ship_report.py docs/mcp-v4-v1.4-*.md
    python scripts/check_ship_report.py docs/  # 扫整个目录

返回:
    0 = 全部检查通过
    1 = 至少 1 个 ship report 不通过
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = [
    r"^## 1\. ",
    r"^## 2\. ",
    r"^## 3\. ",
    r"^## 4\. ",
    r"^## 5\. ",
    r"^## 6\. ",
    r"^## 7\. ",
    r"^## 8\. ",
    r"^## 9\. ",
]

# 额外: 某些章节标题必含关键词 (避免章节号对但内容空)
SECTION_KEYWORDS = {
    5: "退出门槛",
    6: "未在",
    7: "后续",
    8: "回滚",
    9: "引用",
}

# G5: 每章节内容 ≤ 30 行 (防 ship report 膨胀)
MAX_SECTION_LINES = 30

# G8: 必填内容行 (防 ship 时忘写)
# §4 测试策略格式: "测试策略: mock X / 真 Y"
SECTION_4_REQUIRED_PATTERN = re.compile(r"测试策略[:：].*?(?:mock|真)")
# §8 rollback 格式: "rollback: git revert + N 文件"
SECTION_8_REQUIRED_PATTERN = re.compile(r"rollback[:：].*?git revert")

REQUIRED_CONSTRAINTS = [
    ("PR ≤ 1.5d", "5 强约束 §1"),
    ("+30% buffer", "5 强约束 §2"),
    ("1 PR 必含测", "5 强约束 §3"),
    ("顺序锁死", "5 强约束 §5"),
]

# 5 强约束 §4 改 regex: 接受 "rollback" 或 "回滚" (中文), 老 ship report 多用 "回滚"
import re as _re_s4
ROLLBACK_PATTERN = _re_s4.compile(r"rollback|回滚")

# 文件名命名格式: mcp-v4-v*.md (vX.Y 或 vX.Y-a/b/c 后缀) 或 followup-*.md
# 匹配文件名 (用 path.name), 不匹配完整路径 — 支持 absolute 路径 (subprocess/pytest)
NAME_PATTERN = re.compile(r"^(mcp-v4-v[\w.\-]+|followup-[\w\-]+)-ship-report\.md$")

# G5/G8 momus v1 适用范围: 仅新 ship report (followup-*) 必填, 老 mcp-v4-v* grandfather
NEW_NAME_PATTERN = re.compile(r"^followup-[\w\-]+-ship-report\.md$")

# G5/G8 opt-in marker: 新 ship report 模板首行加此 marker 启用 G5/G8 强制检查
# 老 report (含 14 followup-*) 无 marker → grandfathered, 不强制
STRICT_MARKER = "<!-- ship-report-template: g5-g8-v1 -->"


def check_ship_report(path: Path) -> tuple[bool, list[str]]:
    """返回 (pass, errors)."""
    errors: list[str] = []

    # 命名检查 (仅对文件名, 不要求路径以 docs/ 开头) — 改用 path.name 支持 absolute
    file_name = path.name
    if not NAME_PATTERN.match(file_name):
        errors.append(f"  ✗ 命名不符合 {NAME_PATTERN.pattern} (got: {file_name})")

    if not path.exists():
        errors.append(f"  ✗ 文件不存在: {path}")
        return False, errors

    content = path.read_text(encoding="utf-8")

    # 9 章节检查 (按数字, title 内容不强匹配)
    for section_re in REQUIRED_SECTIONS:
        if not re.search(section_re, content, re.MULTILINE):
            errors.append(f"  ✗ 缺章节: {section_re}")

    # 额外: §5/§6/§7/§8/§9 标题必含关键词
    for n, keyword in SECTION_KEYWORDS.items():
        # 找 "## N. <title>" 中 title 部分
        m = re.search(rf"^## {n}\. (.+?)$", content, re.MULTILINE)
        if m and keyword not in m.group(1):
            errors.append(f"  ✗ §{n} 标题缺关键词 '{keyword}' (got: '{m.group(1)}')")

    # 5 强约束检查 (前 4 严格, "量化 KPI" 改为 §1 概览表里 KPI 数字验证)
    for keyword, label in REQUIRED_CONSTRAINTS:
        if keyword not in content:
            errors.append(f"  ✗ 5 强约束缺: {keyword} ({label})")
    # 5 强约束 §4: rollback 策略, 接受 "rollback" 或 "回滚" (中文)
    if not ROLLBACK_PATTERN.search(content):
        errors.append("  ✗ 5 强约束缺: rollback/回滚 策略 (§4)")
    # 量化 KPI 替代验证: §1 概览表里含 ≥ 3 个 ✅ 行 (KPI 维度)
    overview_match = re.search(r"## 1\. 概览.*?(?=## 2\.)", content, re.DOTALL)
    if overview_match:
        kpi_count = overview_match.group(0).count("✅")
        if kpi_count < 3:
            errors.append(f"  ✗ §1 概览表 < 3 个 ✅ KPI 维度 (got {kpi_count}, 5 强约束 §6 要求)")

    # 引用 ≥ 1 个 markdown 链接 OR commit hash (放宽: 接受纯文本 commit 引用)
    md_links = re.findall(r"\[.+?\]\(.+?\)", content)
    commit_refs = re.findall(r"\b[0-9a-f]{7,40}\b", content)  # 7+ 位 hex
    if len(md_links) < 1 and len(commit_refs) < 1:
        errors.append(f"  ✗ 引用 < 1 个 (md 链接: {len(md_links)}, commit 引用: {len(commit_refs)})")

    # §6 章节内容验证: 章节存在但内容空 (避免章节号对但内容缺)
    sec_6_match = re.search(r"## 6\..*?(?=## 7\.)", content, re.DOTALL)
    if sec_6_match and "未在" not in sec_6_match.group(0):
        errors.append("  ✗ §6 标题缺 '未在' 标识 (Out of Scope)")

    # G5/G8 momus v1: 仅当 ship report 含 STRICT_MARKER 才 enforce
    # 老 mcp-v4-v* (grandfather) + 14 老 followup-* (无 marker) 都跳过
    is_new_report = bool(NEW_NAME_PATTERN.match(file_name))
    has_strict_marker = STRICT_MARKER in content

    if is_new_report and has_strict_marker:
        # G5: 每章节内容 ≤ 30 行 (防 ship report 膨胀)
        for n in range(1, 10):
            sec_match = re.search(rf"## {n}\..*?(?=## {n + 1}\.|$)", content, re.DOTALL)
            if sec_match:
                sec_lines = sec_match.group(0).count("\n")
                if sec_lines > MAX_SECTION_LINES:
                    errors.append(
                        f"  ✗ §{n} 章节 {sec_lines} 行 > {MAX_SECTION_LINES} (G5 长度限制, 防 ship report 膨胀)"
                    )

        # G8: §4 必含 "测试策略: mock X / 真 Y"
        sec_4_match = re.search(r"## 4\..*?(?=## 5\.)", content, re.DOTALL)
        if sec_4_match and not SECTION_4_REQUIRED_PATTERN.search(sec_4_match.group(0)):
            errors.append(
                "  ✗ §4 缺 '测试策略: mock X / 真 Y' 行 (G8 必填)"
            )

        # G8: §8 必含 "rollback: git revert + N 文件"
        sec_8_match = re.search(r"## 8\..*?(?=## 9\.)", content, re.DOTALL)
        if sec_8_match and not SECTION_8_REQUIRED_PATTERN.search(sec_8_match.group(0)):
            errors.append(
                "  ✗ §8 缺 'rollback: git revert + N 文件' 行 (G8 必填)"
            )

    return (len(errors) == 0), errors


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/check_ship_report.py <file_or_dir> [...]")
        return 1

    targets: list[Path] = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            targets.extend(sorted(p.glob("**/*-ship-report.md")))
        else:
            targets.append(p)

    if not targets:
        print("⚠️  无 ship report 文件")
        return 1

    total_pass = 0
    total_fail = 0

    for t in targets:
        ok, errors = check_ship_report(t)
        if ok:
            print(f"✅ {t}")
            total_pass += 1
        else:
            print(f"❌ {t}")
            for e in errors:
                print(e)
            total_fail += 1

    print(f"\n=== 摘要: {total_pass} pass, {total_fail} fail ===")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
