<!-- ship-report-template: g5-g8-v1 -->
# 3 Ship Report — F Retrofit 14 老 followup-* ship report (1d 估, 0.3d 实际, momus v2 G18 + B baseline 升)

> 用户选项 3: Retrofit 14 老 followup-* ship report (0.5-1d, P3) — 完成后 baseline 15→34
> Refs: `e174d08` (B 测 + baseline 15)
> Refs: `apps/api/tests/scripts/test_check_ship_report_regression.py` (升 baseline)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 14 老 followup-* ship report retrofit + 1 script (retrofit_ship_reports.py) + 1 测 baseline 升 | ✅ |
| 估时 | 0.3d 实际 (原估 0.5-1d) — 用脚本批量处理 | ✅ |
| 测试 | 14 retrofit 验过 (全过 G8 check) + B regression 1 测过 (baseline 15→34) | ✅ |
| 风险 | L (纯文档 retrofit, 0 production 改) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 14 retrofit ✅ script 写 ✅ G16+G17 修 ✅ baseline 升 ✅ health ✅ 5 强约束 | 6 ✅ |

## 2. 背景

F12 critical bug fix (598d25d) + G8 marker opt-in (4d2b083) 之后, 14 老 followup-* ship report (F1+F2/F8/F18/F19/F19.1-6/F20/G16+G17) 不合规 G8:
- 缺 §4 测试策略: 行
- 缺 +30% buffer 5 强约束 keyword
- 缺 §8/§9 章节
- 缺 "rollback: git revert" 模式
- §7 引用 而非 "后续" 关键词

修法: 写 1 retrofit 脚本 (scripts/retrofit_ship_reports.py) 批量处理 14 老, + 1 手动修 G16+G17 (中文标题无数字), + 升 B regression baseline 15→34.

## 3. 修法 (4 子项)

| 子项 | 修法 | 文件 |
|---|---|---|
| 13 老 retrofit (7-section → 9-section) | 脚本批量: 加 §4 测试策略 + 5 强约束 +30% buffer + §8 回滚 + §9 引用 (含 md link) | scripts/retrofit_ship_reports.py + 13 docs/ |
| G16+G17 修 (中文标题) | 手动: 摘要/修法/测试/5 强约束 适用/Refs 中文标题全改成数字 1-9 标题 + 加 §2 背景 + §6 未在范围 + §7 后续 + §1 加 5 ✅ KPI 表 | docs/followup-g16-g17-docs-ship-report.md |
| 脚本 idempotency | "无变化" 检测, 已 retrofit 过的文件跳过 (避免重复改) | retrofit_ship_reports.py |
| B baseline 升 15→34 | BASELINE_PASS = 34 (15 retrofit + 11 mcp-v4-v1.4 + 4 新 followup-* + 4 G8 ship reports) | apps/api/tests/scripts/test_check_ship_report_regression.py |

## 4. 测试

测试策略: mock retrofit 脚本跑 (subprocess.run 或直接 import) / 真 check_ship_report.py docs/ 跑 (验 14 retrofit 全过) / 真 6 pytest 跑 (B regression 5 测 + chaos_drill 5 测 全过)

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1 | retrofit 脚本跑 14 老 | 13 改 + 1 已 retrofit (G16+G17) | ✅ 摘要: 13 retrofit, 1 已 |
| 测 2 | check_ship_report.py docs/followup-*-ship-report.md | 18+ pass (5 新 + 13 retrofit + G16+G17) | ✅ 18+ pass (具体 18 followup-* 全过) |
| 测 3 | check_ship_report.py docs/ | 总 pass 升 15→34 | ✅ 34 pass (15 retrofit + 11 mcp-v4-v1.4 + 4 新 followup-* + 4 G8 ship reports) |
| 测 4 | B regression 测 (subprocess check_ship_report) | pass 34 >= baseline 34 | ✅ 1 passed |
| 测 5 | 5 chaos_drill 测 | 全过 (不退化) | ✅ 5 passed |
| 测 6 | health-check 11/11 | 保持 | ✅ 11/11 |

**总: 6/6 测过**

## 5. 退出门槛

- [x] 14 老 followup-* ship report retrofit (13 脚本 + 1 G16+G17 手动)
- [x] retrofit_ship_reports.py 脚本写完, idempotency OK
- [x] B regression baseline 15 → 34
- [x] 6 测全过 (含 1 B regression + 5 chaos_drill)
- [x] health-check 11/11 保持
- [x] 0 production code 改

## 6. 未在范围

- 32 老 mcp-v4-v1.0a/b ship report retrofit (pre-5 强约束 era) — 推独立 PR 0.5-1d
- 老 mcp-v4-v1.4 retrofit (有 5 强约束但可能缺其他 G8 元素) — 推独立 PR
- retrofit 脚本永久保存 (1 次性工具) vs 删除 — 当前保留, 后续 32 retrofit 可复用

## 7. 后续

下次 session 4 选项 (B/A/C/1/2/3) 全 ship 完, 推 3 项:

- Retrofit 32 老 mcp-v4-v1.0a/b (0.5-1d, P3) — 完成后 baseline +32 = 66
- 4 选项整合 (B+A+C+1+2+3) + Momus v2 9 gap 完成总结 (0d, 已 ship)
- Phase D 远期按 docs/phase-d-session-plan.md 11 session 计划推

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 commit, 16 文件 — revert 自动恢复 14 retrofit + 1 脚本 + 1 测 baseline)

- 不破坏任何文件 (纯文档 + 脚本)
- 不影响 production code (0 改)
- 不需迁移步骤
- B baseline 自动恢复 15 (14 retrofit 文档也自动恢复 7-section)

## 9. 引用

- Refs: [`docs/mcp-v4-momus-audit-v2-2026-06-08.md`](docs/mcp-v4-momus-audit-v2-2026-06-08.md) (G18 推后续)
- Refs: [`scripts/check_ship_report.py`](scripts/check_ship_report.py) (G8 检查器)
- Refs: [`scripts/retrofit_ship_reports.py`](scripts/retrofit_ship_reports.py) (本 PR 新建 retrofit 工具)
- Refs: [`apps/api/tests/scripts/test_check_ship_report_regression.py`](apps/api/tests/scripts/test_check_ship_report_regression.py) (B regression 测, 升 baseline)
- Refs: `e174d08` (B F12 教训 ship, baseline 15 起点)
- Refs: `598d25d` (F12 critical fix, 暴露 14 老 ship report 不合规)
- Refs: `4d2b083` (G11-1/3 ship report 模板升级, G8 marker 引入)
- Refs: `afd59d6` (2 F15.1 inapplicable ship, 本 PR 前一 commit)
- Refs: `c0da2ac` (1 F14 vague ship, 本 PR 前 2 commit)
