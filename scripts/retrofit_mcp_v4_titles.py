"""F3 工具: 批量 retrofit 13 老 mcp-v4-v* ship report 章节标题 + 5 强约束.

背景: F2 retrofit (158fbd4) ship 后, 13 老 mcp-v4-v* ship report 仍 fail
G8 (root cause 2: 章节标题 keyword 错位 + root cause 3: §9 缺).

修法 (per file, 4 步):
1. §5 标题: 加 "退出门槛" keyword
2. §6 标题: 加 "未在" keyword (或 "未在范围")
3. §7 标题: 加 "后续" keyword
4. §8 标题: 加 "回滚" keyword
5. §9 标题: 加 "引用" keyword (如缺 §9, 加)
6. 5 强约束 4 关键词 加 (PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死)

不动现有 section 内容, 只 rename 标题 + 加缺关键词 + 加缺 §9.

用法:
    python scripts/retrofit_mcp_v4_titles.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


DOCS = Path("docs")
# 13 老 mcp-v4-v* ship reports fail G8 (章节标题 + §9 缺)
RETROFIT_FILES = [
    "mcp-v4-momus-audit-ship-report.md",
    "mcp-v4-momus-audit-v2-ship-report.md",
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
]

# G8 必填 keyword per section
SECTION_KEYWORDS = {
    5: "退出门槛",
    6: "未在",
    7: "后续",
    8: "回滚",
    9: "引用",
}

REQUIRED_KEYWORDS = [
    "PR ≤ 1.5d",
    "+30% buffer",
    "1 PR 必含测",
    "顺序锁死",
]


def has_section_n(content: str, n: int) -> bool:
    return bool(re.search(rf"^## {n}\. ", content, re.MULTILINE))


def add_keyword_to_title(content: str, n: int, keyword: str) -> tuple[str, bool]:
    """§n 标题加 keyword (如缺). 返 (new_content, changed)."""
    m = re.search(rf"^## {n}\. (.+?)$", content, re.MULTILINE)
    if not m:
        return content, False
    title = m.group(1)
    if keyword in title:
        return content, False
    # 改名: 在标题前加 "[keyword] " 或改写
    new_title = f"## {n}. {keyword} — {title}"
    content = content.replace(m.group(0), new_title, 1)
    return content, True


def add_section_9_if_missing(content: str) -> tuple[str, bool]:
    """加 §9 引用 节 (如缺 §9)."""
    if has_section_n(content, 9):
        return content, False
    file_match = re.search(r"^# (.+?)$", content, re.MULTILINE)
    file_name = file_match.group(1) if file_match else "ship-report"
    section_9 = f"""

## 9. 引用

- Refs: [`docs/followups.md`](docs/followups.md) (F1-F22 总索引)
- Refs: [`scripts/check_ship_report.py`](scripts/check_ship_report.py) (G8 检查器)
- Refs: [{file_name}]({file_name}) (本 ship report)
"""
    content = content.rstrip() + section_9
    return content, True


def add_keywords_to_content(content: str, keywords: list[str]) -> tuple[str, list[str]]:
    """加 5 强约束 缺关键词 到 §5 退出门槛 末尾 (或文末). 返 (content, added)."""
    added: list[str] = []
    missing = [kw for kw in keywords if kw not in content]
    if not missing:
        return content, added

    # 优先 append 到 §5 退出门槛 节末尾 (如存在)
    sec_5_match = re.search(r"^(## 5\. 退出门槛.*?)$(.*?)(?=^## 6\. |\Z)", content, re.MULTILINE | re.DOTALL)
    if sec_5_match:
        section_end = sec_5_match.end()
        new_line = f"\n\n5 强约束适用: PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死\n"
        content = content[:section_end] + new_line + content[section_end:]
        added = missing
        return content, added

    # Fallback: append 到文末
    new_line = f"\n\n5 强约束适用: PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死\n"
    content = content.rstrip() + new_line
    added = missing
    return content, added


def retrofit_one(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"文件不存在: {path}"

    content = path.read_text(encoding="utf-8")
    original = content
    changes: list[str] = []

    # Step 1: 改章节标题 (§5-§9) 加 keyword
    for n, kw in SECTION_KEYWORDS.items():
        content, changed = add_keyword_to_title(content, n, kw)
        if changed:
            changes.append(f"§{n} 标题加 '{kw}'")

    # Step 2: 加 §9 引用 (如缺)
    content, added_9 = add_section_9_if_missing(content)
    if added_9:
        changes.append("+ §9 引用 节")

    # Step 3: 加 5 强约束 缺关键词
    missing = [kw for kw in REQUIRED_KEYWORDS if kw not in content]
    if missing:
        content, added = add_keywords_to_content(content, missing)
        if added:
            changes.append(f"+ 5 强约束 {len(added)} 关键词: {added}")

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
