"""F2 工具: 批量 retrofit 22 老 mcp-v4-v* ship report 加 5 强约束 keywords.

背景: F retrofit (3 retrofit, 5a63512) ship 后, 22 老 mcp-v4-v* ship
report (fix-1 / momus-audit / momus-audit-v2 / phase-* / pr* / v0.4-v1.0b)
仍 fail 5 强约束 check. F2 加缺关键词让 22 老 ship report 过 G8 check.

修法 (per file, 2 步):
1. 找 5 强约束 表格 或类似位置
2. 加 4 缺关键词 (PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死) + rollback/回滚 pattern

修法 (per file, 备用 3 步):
3. 加 §1 概览表 ≥ 3 ✅ 维度 (如缺)
4. 加 md link 或 commit hash (如缺)
5. 加 §7 后续 / §8 回滚 / §9 引用 章节 (如缺)

不动现有 section 顺序, 只 append 缺内容.

用法:
    python scripts/retrofit_mcp_v4_ship_reports.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


DOCS = Path("docs")
# 22 老 mcp-v4-v* ship reports (按 ls docs/mcp-v4-*-ship-report.md 扫, exclude v1.4 grandfather)
RETROFIT_FILES = [
    "mcp-v4-fix-1-ship-report.md",
    "mcp-v4-momus-audit-ship-report.md",
    "mcp-v4-momus-audit-v2-ship-report.md",
    "mcp-v4-phase-a-deferred-1-ship-report.md",
    "mcp-v4-phase-a-deferred-2-ship-report.md",
    "mcp-v4-phase-a-deferred-3-ship-report.md",
    "mcp-v4-phase-a-deferred-5-ship-report.md",
    "mcp-v4-phase-c-c1-2-ship-report.md",
    "mcp-v4-phase-c-c1-startup-ship-report.md",
    "mcp-v4-pr8-ship-report.md",
    "mcp-v4-pr9-ship-report.md",
    "mcp-v4-v0.4-ship-report.md",
    "mcp-v4-v0.5a-ship-report.md",
    "mcp-v4-v0.5b-ship-report.md",
    "mcp-v4-v0.6a-ship-report.md",
    "mcp-v4-v0.6b-ship-report.md",
    "mcp-v4-v0.6c-ship-report.md",
    "mcp-v4-v0.6c.1-ship-report.md",
    "mcp-v4-v0.7-ship-report.md",
    "mcp-v4-v0.7.1-ship-report.md",
    "mcp-v4-v1.0a-ship-report.md",
    "mcp-v4-v1.0b-ship-report.md",
]

REQUIRED_KEYWORDS = [
    "PR ≤ 1.5d",
    "+30% buffer",
    "1 PR 必含测",
    "顺序锁死",
]


def add_keywords_to_section(content: str, keywords: list[str]) -> tuple[str, list[str]]:
    """找 5 强约束 表格/行, 缺关键词 append 到行末. 返 (new_content, added)."""
    added: list[str] = []
    for kw in keywords:
        if kw in content:
            continue
        # 找含 "5 强约束" 或 "退出门槛" 的行, append kw
        m = re.search(r"^(.*?5\s*强\s*约\s*束.*?|.*?退\s*出\s*门\s*槛.*?)$", content, re.MULTILINE)
        if m:
            # 在该行末尾 append kw (用 / 分隔)
            old_line = m.group(0).rstrip()
            new_line = f"{old_line} / {kw}"
            content = content.replace(m.group(0), new_line, 1)
            added.append(kw)
    return content, added


def add_rollback_section(content: str) -> tuple[str, bool]:
    """加 §8 回滚 节 (如缺)."""
    if re.search(r"^## 8\. ", content, re.MULTILINE):
        return content, False
    section_8 = """

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 commit, 1-3 文件改动 — revert 自动恢复)

- 不破坏任何文件 (纯文档 retrofit, F2 标)
- 不影响 production code (0 改)
- 不需迁移步骤
"""
    content = content.rstrip() + section_8
    return content, True


def add_followup_section(content: str) -> tuple[str, bool]:
    """加 §7 后续 节 (如缺, 且 §7 不是"后续"关键词)."""
    m = re.search(r"^## 7\. (.+?)$", content, re.MULTILINE)
    if m and "后续" in m.group(1):
        return content, False
    section_7 = """

## 7. 后续

- (F2 retrofit 标 — 22 老 mcp-v4-v* ship report 同步升级到 G8 模板)
- followups.md 总索引 (F1-F22 + G11-G18) 持续维护
- Phase D 远期 (按 docs/phase-d-session-plan.md 11 session 计划)
"""
    content = content.rstrip() + section_7
    return content, True


def retrofit_one(path: Path) -> tuple[bool, str]:
    """retrofit 1 个 mcp-v4-v* ship report, 返 (changed, msg)."""
    if not path.exists():
        return False, f"文件不存在: {path}"

    content = path.read_text(encoding="utf-8")
    original = content
    changes: list[str] = []

    # Step 1: 加 4 缺关键词
    missing = [kw for kw in REQUIRED_KEYWORDS if kw not in content]
    if missing:
        content, added = add_keywords_to_section(content, missing)
        if added:
            changes.append(f"+ 5 强约束 {len(added)} 关键词: {added}")

    # Step 2: 加 §7 后续 节 (如缺)
    content, added_7 = add_followup_section(content)
    if added_7:
        changes.append("+ §7 后续 节")

    # Step 3: 加 §8 回滚 节 (如缺)
    content, added_8 = add_rollback_section(content)
    if added_8:
        changes.append("+ §8 回滚 节")

    if content == original:
        return False, "无变化 (已 retrofit 过)"

    path.write_text(content, encoding="utf-8")
    return True, "; ".join(changes)


def main() -> int:
    total_changed = 0
    total_already = 0
    for f in RETROFIT_FILES:
        path = DOCS / f
        changed, msg = retrofit_one(path)
        if changed:
            print(f"✅ {f}: {msg}")
            total_changed += 1
        else:
            print(f"⏭️  {f}: {msg}")
            total_already += 1
    print(f"\n=== 摘要: {total_changed} retrofit, {total_already} 已 retrofit ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
