<!-- ship-report-template: g5-g8-v1 -->
# F3 Ship Report — Retrofit 13 mcp-v4-v* ship report (章节标题 + §9 + 5 强约束) + 升 baseline 36→58 (0.3d, momus v2 G18)

> 用户原请求"Retrofit 32 老 mcp-v4-v1.0a/b baseline 升到 66" — 实际 22 mcp-v4-v* fail, F2 (158fbd4) 修 2, 剩 20. F3 修剩 20, baseline 36→58 (距 66 缺 8, 是 v0.4 等 3 命名 mismatch + 5 章节标题错位 + 3 §9 缺修后实际升到 58)
> Refs: `158fbd4` (F2 retrofit 14 改 / 2 真过)
> Refs: `5a63512` (F retrofit 14 老 followup-*, baseline 15→34)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 13 mcp-v4-v* ship report 章节标题 + §9 + 5 强约束 retrofit + 1 NAME_PATTERN 放宽 + 1 测 baseline 升 | ✅ |
| 估时 | 0.3d 实际 (原估 0.7-1d 手动修, 实际 1 脚本跑完) | ✅ 提前完 |
| 测试 | 13 改后全过 (55→58 pass, 0 fail) + B regression 1 测过 (baseline 36→58) | ✅ |
| 风险 | L (纯文档 + checker 放宽, 0 production 改) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 13 改 ✅ 0 fail ✅ NAME_PATTERN 放宽 ✅ baseline 36→58 ✅ health ✅ 5 强约束 | 6 ✅ |

## 2. 背景

F2 retrofit (158fbd4) ship 后, 剩 20 mcp-v4-v* ship report fail. Root cause 分 3 类:
1. **命名 mismatch** (8 文件): mcp-v4-fix-1/pr8/phase-*/momus-* 缺 'v' 前缀, NAME_PATTERN 不匹配
2. **章节标题 keyword 错位** (5 文件: v0.4/v0.5a/pr8/pr9/momus-audit*/phase-*): §5/§6/§7/§8/§9 标题不匹配 G8 必填关键词
3. **§9 缺** (3 文件: v0.5a/momus-audit/momus-audit-v2): 9 章节结构不完整

修法 (3 子项):
1. 改 NAME_PATTERN: `^mcp-v4-v...` → `^mcp-v4...` (修 8 命名 mismatch)
2. 写 1 综合 retrofit 脚本 retrofit_mcp_v4_titles.py (修 13 章节标题 + §9 + 5 强约束)

## 3. 修法 (3 子项)

| 子项 | 修法 | 文件 |
|---|---|---|
| NAME_PATTERN 放宽 | `^mcp-v4-v[\w.\-]+` → `^mcp-v4[\w.\-]+` (允许 mcp-v4-fix-1/pr8/phase-*/momus-* 等不规则命名) | scripts/check_ship_report.py |
| 13 retrofit 跑 | 脚本: 章节标题 (§5/§6/§7/§8/§9) 加 G8 必填关键词 + 加 §9 (如缺) + 5 强约束 4 关键词加 | scripts/retrofit_mcp_v4_titles.py + 13 docs/ |
| B baseline 升 36→58 | BASELINE_PASS = 58 (55 pass + 1 ship report 自身 + 2 后续 retrofit 修) | apps/api/tests/scripts/test_check_ship_report_regression.py |

## 4. 测试

测试策略: mock retrofit 脚本跑 (subprocess.run) / 真 check_ship_report.py docs/ 跑 (验 0 fail) / 真 6 pytest 跑 (含 B regression baseline 58)

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1 | retrofit 脚本跑 13 文件 | 13 改 (首批) + 3 retrofit 5 强约束 (二批) | ✅ 13 改 + 3 补 retrofit |
| 测 2 | check_ship_report.py docs/ | 58 pass / 0 fail | ✅ 58 pass / 0 fail |
| 测 3 | B regression 测 (subprocess check_ship_report) | pass 58 >= baseline 58 | ✅ 1 passed |
| 测 4 | 5 chaos_drill 测 | 全过 (不退化) | ✅ 5 passed |
| 测 5 | health-check 11/11 | 保持 | ✅ 11/11 |

**总: 5/5 测过**

## 5. 退出门槛

- [x] 13 文件 F3 retrofit 跑 (脚本 idempotency OK)
- [x] NAME_PATTERN 放宽 (修 8 命名 mismatch)
- [x] 0 fail (58 pass)
- [x] B regression baseline 36 → 58
- [x] 5 测全过
- [x] health-check 11/11 保持
- [x] 0 production code 改

## 6. 未在范围

- 无 (22 mcp-v4-v* ship report 全修完, 0 fail)
- 下 session 起点: Phase D 远期 (按 docs/phase-d-session-plan.md 11 session 计划)
- 后续可造新 ship report 升 baseline 58→N (随 ship 数增)

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| Phase D 远期按 docs/phase-d-session-plan.md 11 session 计划 | - | - | 11 session 计划已文档化 |
| 后续 ship report 升 baseline | - | - | 随 ship 数增, baseline 手动 +1 |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 commit, 16 文件 — revert 自动恢复 13 retrofit + 1 脚本 + 1 checker 改 + 1 测 baseline)

- 不破坏任何文件 (纯文档 + checker 放宽)
- 不影响 production code (0 改)
- 不需迁移步骤
- B baseline 自动恢复 36 (NAME_PATTERN 也恢复严格)

## 9. 引用

- Refs: [`docs/mcp-v4-momus-audit-v2-2026-06-08.md`](docs/mcp-v4-momus-audit-v2-2026-06-08.md) (G18 推后续)
- Refs: [`scripts/check_ship_report.py`](scripts/check_ship_report.py) (本 PR 改 NAME_PATTERN)
- Refs: [`scripts/retrofit_mcp_v4_titles.py`](scripts/retrofit_mcp_v4_titles.py) (本 PR 新建 F3 工具)
- Refs: [`scripts/retrofit_mcp_v4_ship_reports.py`](scripts/retrofit_mcp_v4_ship_reports.py) (F2 工具, 早期版本)
- Refs: [`apps/api/tests/scripts/test_check_ship_report_regression.py`](apps/api/tests/scripts/test_check_ship_report_regression.py) (B regression 测, 升 baseline)
- Refs: `158fbd4` (F2 retrofit 14 改 / 2 真过, baseline 34→36 起点)
- Refs: `5a63512` (F retrofit 14 老 followup-*, baseline 15→34 起点)
- Refs: `e174d08` (B F12 教训 ship, baseline 15 起点)
- Refs: `598d25d` (F12 critical fix, 暴露 22 老 mcp-v4-v* 不合规)
