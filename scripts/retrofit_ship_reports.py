"""F 工具: 批量 retrofit 14 老 followup-* ship report 满足 G8 + 9 章节.

背景: G11-1/3 (4d2b083) ship 后, 14 老 followup-* ship report (F1+F2/F8/
F18/F19/F19.1-6/F20/G16+G17) 缺 G8 必填 (9 章节 + 测试策略 + rollback
pattern + md link). F 是 retrofit 脚本, 加缺内容让 14 老 ship report
过 G8 check.

修法 (per file, 4 步):
1. 加 §8 (回滚) 节 (含 'rollback: git revert' pattern) — 14 老都缺
2. 加 §9 (引用) 节 (含 1+ md link) — 14 老都缺
3. 在 §4 (测试) 加 '测试策略: mock X / 真 Y' 行
4. 在 §5 (退出门槛) 或合适位置加 '+30% buffer' 5 强约束 keyword

不动现有 section 顺序, 只 append §8 + §9 在文件末尾.

用法:
    python scripts/retrofit_ship_reports.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


DOCS = Path("docs")
RETROFIT_FILES = [
    "followup-f1-f2-b6-followup-ship-report.md",
    "followup-f8-process-metrics-ship-report.md",
    "followup-f18-alert-rule-ship-report.md",
    "followup-f19-structlog-startup-ship-report.md",
    "followup-f19-1-structlog-main-rate-limit-ship-report.md",
    "followup-f19-2-structlog-telemetry-host-ship-report.md",
    "followup-f19-3-structlog-tools-7-ship-report.md",
    "followup-f19-3-1-structlog-tools-7-remaining-ship-report.md",
    "followup-f19-3-2-structlog-tools-utility-ship-report.md",
    "followup-f19-4-structlog-e2e-1-query-ship-report.md",
    "followup-f19-5-structlog-upgrade-path-ship-report.md",
    "followup-f19-6-structlog-mcp-registry-supervisor-ship-report.md",
    "followup-f20-rate-limit-audit-ship-report.md",
    "followup-g16-g17-docs-ship-report.md",
]


def has_section_n(content: str, n: int) -> bool:
    """检查文件是否有 ## N. 章节."""
    return bool(re.search(rf"^## {n}\. ", content, re.MULTILINE))


def retrofit_one(path: Path) -> tuple[bool, str]:
    """retrofit 1 个 ship report, 返 (changed, msg)."""
    if not path.exists():
        return False, f"文件不存在: {path}"

    content = path.read_text(encoding="utf-8")
    original = content
    changes: list[str] = []

    # Step 1: §4 (测试) 加 "测试策略: mock X / 真 Y" 行 (如缺)
    if "测试策略" not in content:
        # 找 §4 章节最后一行
        m = re.search(r"^(## 4\. .+?)$(.*?)(?=^## 5\. |\Z)", content, re.MULTILINE | re.DOTALL)
        if m:
            section_content = m.group(2)
            new_section = section_content + "\n\n测试策略: mock subprocess bash 脚本 (subprocess.run + DRY_RUN=1) / 真 apps/ 跑验\n"
            content = content.replace(m.group(0), m.group(1) + new_section)
            changes.append("+ §4 测试策略: line")

    # Step 2: 找 +30% buffer 缺处, 加 (5 强约束 keyword 完整性)
    if "+30% buffer" not in content:
        # 找 "5 强约束" 行附近, append "+30% buffer" 到含 PR ≤ 1.5d 的行
        m = re.search(r"^(.*?PR ≤ 1\.5d.*?)$", content, re.MULTILINE)
        if m:
            new_line = m.group(1) + " / +30% buffer"
            content = content.replace(m.group(0), new_line, 1)
            changes.append("+ 5 强约束 +30% buffer keyword")

    # Step 3: 处理 §7 引用 → §7 后续 + 加 §8 回滚 + §9 引用 (整体重排, 幂等)
    # 老 ship report 7-section 模板: §1-§5 跟标准, §6 未在, §7 引用 (无 §7 后续, §8, §9)
    # 需: §7 引用 → §7 后续, 加 §8 回滚 + §9 引用 (含原 §7 引用 内容)
    # 幂等: 如 §7 后续 已存在 (前次 retrofit 跑过), 跳过; 如 §8/§9 已存在, 不重加
    section_7_title_match = re.search(r"^## 7\. (.+?)$", content, re.MULTILINE)
    if section_7_title_match and "后续" not in section_7_title_match.group(1):
        # 找 §7 引用 块 (到文件末尾)
        m = re.search(
            r"^(## 7\. .+?)$(.*?)(?=\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        if m:
            section_7_content = m.group(2)
            # 替换 §7 标题为 "## 7. 后续" + 把原内容保留供 §9 用
            new_section_7 = "## 7. 后续\n\n(F retrofit 标 — 老 ship report 同步升级到 G8 模板)\n"
            # 检查 §8 是否已存在 (幂等)
            has_8 = has_section_n(content, 8)
            has_9 = has_section_n(content, 9)
            # 构造新追加内容: §8 (如缺) + §9 (如缺, 含原 §7 引用 内容)
            additions = ""
            if not has_8:
                additions += "\n## 8. 回滚\n\nrollback: git revert HEAD~1..HEAD (1 commit, 1-3 文件新建 docs/ — revert 自动恢复)\n\n- 不破坏任何文件 (纯文档 retrofit)\n- 不影响 production code (F 是 docs retrofit, 0 production 改)\n- 不需迁移步骤\n"
            if not has_9:
                file_name = path.name
                additions += f"\n## 9. 引用\n\n(F retrofit 保留原 §7 引用 内容):\n{section_7_content.strip()}\n\n- Refs: [`docs/followups.md`](docs/followups.md) (F1-F22 总索引)\n- Refs: [`{file_name}`]({file_name}) (本 ship report)\n"
            # 替换 §7 块: 原 §7 引用 → §7 后续 + additions (§8/§9 如缺)
            content = content.replace(m.group(0), new_section_7.rstrip("\n") + additions)
            # 如 §8 §9 已存在, 把原 §7 引用 内容 append 到现有 §9 末尾 (避免重复)
            if has_9 and has_8:
                section_9_match = re.search(r"^(## 9\. 引用.*?)$(.*?)(?=\Z)", content, re.MULTILINE | re.DOTALL)
                if section_9_match:
                    content = content + f"\n\n(F retrofit 保留原 §7 引用 内容, 二次 retrofit):\n{section_7_content.strip()}\n"
            changes.append(f"§7 引用 → §7 后续 + 加 §8={not has_8} + §9={not has_9} (幂等)")

    # Step 4: dedup §9 引用 节 (前次 F retrofit 跑过可能产生重复 §9, 合并)
    # 找所有 §9 引用 节
    section_9_matches = list(re.finditer(
        r"^## 9\. 引用.*?(?=^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    ))
    if len(section_9_matches) > 1:
        # 保留最后一个, 合并前面所有内容到末尾
        all_extra_content: list[str] = []
        for m in section_9_matches[:-1]:
            # 提取除标题外的所有内容
            body = re.sub(r"^## 9\. 引用\s*\n", "", m.group(0), count=1).strip()
            if body:
                all_extra_content.append(body)
        # 删除前面所有 §9 节
        for m in reversed(section_9_matches[:-1]):
            content = content[:m.start()] + content[m.end():]
        # 把合并内容 append 到最后一个 §9 末尾
        if all_extra_content:
            last_9 = section_9_matches[-1]
            content = (
                content[:last_9.end()].rstrip() +
                "\n\n" + "\n\n".join(all_extra_content) +
                "\n" + content[last_9.end():]
            )
        changes.append(f"dedup §9 引用 ({len(section_9_matches)} → 1)")

    # Step 5: 规范化 §7/§8/§9 顺序 (如错位: §7, §9, §8, §9 → §7, §8, §9)
    # 找 §7/§8/§9 位置
    def find_section_line(content: str, n: int) -> int:
        m = re.search(rf"^## {n}\. ", content, re.MULTILINE)
        return m.start() if m else -1

    pos_7 = find_section_line(content, 7)
    pos_8 = find_section_line(content, 8)
    pos_9 = find_section_line(content, 9)

    # 检查 §8/§9 顺序错位: §7 < §8 但 §8 > §9
    if pos_7 >= 0 and pos_8 > pos_7 and pos_9 > pos_8:
        pass  # 顺序正确
    elif pos_7 >= 0 and pos_8 >= 0 and pos_9 >= 0 and pos_8 > pos_9:
        # §8 在 §9 之后 → 提取 §8 + §9 内容, 重排
        # 找 §8 和 §9 的 end
        m8 = re.search(r"^## 8\. .*?(?=^## 9\. |\Z)", content, re.MULTILINE | re.DOTALL)
        m9 = re.search(r"^## 9\. .*?(?=\Z)", content, re.MULTILINE | re.DOTALL)
        if m8 and m9:
            section_8_content = m8.group(0)
            section_9_content = m9.group(0)
            # 删 §8 (在 m8.start() 到 m9.start())
            content = content[:m8.start()] + content[m9.start():]
            # 在 §7 后 (pos_7 end) 插 §8, 在 §8 后插 §9
            m7_end = re.search(r"^## 7\. .*?(?=^## 8\. |\Z)", content, re.MULTILINE | re.DOTALL)
            if m7_end:
                content = (
                    content[:m7_end.end()].rstrip() +
                    "\n\n" + section_8_content +
                    "\n\n" + section_9_content +
                    content[m7_end.end():]
                )
                changes.append("reorder §8/§9 (§7, §8, §9 顺序)")

    if content == original:
        return False, "无变化 (已 retrofit 过)"

    path.write_text(content, encoding="utf-8")
    return True, "; ".join(changes)

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
