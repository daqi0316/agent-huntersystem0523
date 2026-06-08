# Momus 深度审核 Ship Report — 2026-06-08 (10 gap + 4 修复 + followups 总索引)

> **Ship 日期**: 2026-06-08
> **类型**: Momus (Plan Critic) 复审 + 修正 + 总索引创建
> **依据**: 前次 momus (2026-06-07 complete-roadmap-momus-review.md) 6 维度初审核 + 本会话 13 commit 实施情况
> **上一站**: `Phase C C1.2` (e2c6bcc + d8f1b72) — 2026-06-08 (Grafana dashboard)
> **commit**: 1 个 docs (4 文件)
> **接受门槛**: 10 gap 找全 + G1+G2+G3+G4 P0/P1 顺手修 + followups 总索引 22 项 + plan 修正 3 处

## 1. 概览

| 维度 | 状态 |
|---|---|
| 10 gap 找全 (3 P0 + 4 P1 + 3 P2) | ✅ momus audit 报告 |
| G1 5 强约束适用边界 | ✅ plan §7 改 (代码/docs/config/启动 PR 4 边界) |
| G2 Phase A 推后 (4) workers 显式 skip | ✅ plan §7 加"显式 skip"段 |
| G3 Phase E placeholder | ✅ plan §5.5 加 (E1/E2/E3, 1.5-3.5d) |
| G4 B3 跳因明说 | ✅ plan §5.2 改 (v0.8 Router 已有 30+ E2E) |
| G6 followups 总索引 | ✅ docs/followups.md 22 项 (估 ~25d) |
| G5+G7+G8+G9+G10 推后续 PR | ⏸️ 跨多 session |
| 0 行 production code 改 | ✅ 纯 docs + plan 修正 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `docs/mcp-v4-momus-audit-2026-06-08.md` | +180 / -0 | momus 6 维度复审, 10 gap + 修正建议 + 优先级 |
| `docs/followups.md` | +95 / -0 | 22 推后项总索引 + 推荐下次 session 起点 |
| `.omo/plans/2026-06-07-roadmap-corrected.md` | +20 / -4 | 3 处修正 (G1 §7 / G3 §5.5 / G4 §5.2) + 1 处说明 (G2 §7 推后 skip) |
| **总** | **+295 / -4** | 3 文件 (含 1 规划) |

## 3. 10 Gap 摘要 (G1-G10)

| Gap | 严重度 | 修正 | 状态 |
|---|---|---|---|
| G1 5 强约束适用边界 | P0 | plan §7 测试 + rollback 补充 4 边界 | ✅ 本 PR 修 |
| G2 (4) workers 显式 skip | P0 | plan §7 加"显式 skip"段 | ✅ 本 PR 修 |
| G3 Phase E placeholder | P0 | plan §5.5 加 E1/E2/E3 | ✅ 本 PR 修 |
| G4 B3 跳因明说 | P1 | plan §5.2 B3 行加注释 | ✅ 本 PR 修 |
| G5 ship report 模板 | P1 | A6 check_ship_report.py 升级 | 推后续 PR |
| G6 followups 总索引 | P1 | docs/followups.md | ✅ 本 PR 修 |
| G7 防御 check 升级 | P1 | check_baseline_run.py + check_e2e_run.py | 推后续 PR |
| G8 ship report 模板加 2 行 | P2 | 改 A6 模板 | 推后续 PR |
| G9 C1.2 proxy 后续 | P2 | Backend 加 process_* 暴露 | 推后续 PR (F8) |
| G10 health 跨 session 监控 | P2 | C1.3 alert | 推后续 PR (F18) |

**本 PR 修 4 P0/P1 (G1+G2+G3+G4+G6), 5 推后续 PR (G5+G7+G8+G9+G10), 估 ~1d 总跨多 session**

## 4. followups 总索引 (docs/followups.md) 摘要

**22 推后项, 估 ~25d 总**:

| 类别 | 项 | 估时 | 优先级 |
|---|---|---|---|
| B6 完整推后 | F1 real-flow 429 / F2 auth UI selector | 0.5d | P1 |
| Playwright 集成架构 | F3-F5 root cause / upstream / 18 spec CI | 1.6d+ | P2-P3 |
| Fix-1 + Phase A 推后 | F6 mcp_host / F7 workers skip / F9 A2 install / F10 perf baseline | 0d | P2-P3 |
| C1.2 后续 (本会话新发现) | F8 Backend 加 process_* | 0.2d | P1 |
| A6 推后 | F11 retro-fit / F12 CI lint | 0.8d | P2 |
| B2/B5 推后 | F13 SQL / F14 fixture FK | 0.8d | P2 |
| PR-1a | F15 test_server_restart_on_kill | 1-2d | P2 |
| Phase D 8 PR | F22 D1-D8 | 15d | P3 |
| Phase C 4 PR | F18-F21 C1.3/C2.x | 3.3d | P1 |
| momus 推后续 | F16 Phase E / F17 check 升级 | 1.8-3.8d | P2-P3 |

**推荐下次 session 起点**: F8 (Backend 加 process_*) + F18 (C1.3 alert), 1.5-2d 估时, 1 PR ≤ 1.5d 内 ship 2 PR.

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 10 gap 找全 | momus audit 报告 4 维度覆盖 | ✅ |
| G1+G2+G3+G4 顺手修 | plan 3 处 edit | ✅ |
| G6 followups 总索引 | docs/followups.md 22 项 | ✅ |
| 0 行 production code 改 | git diff 范围仅 docs/ + plan | ✅ |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.4d (4 docs) | ✅ |
| 5 强约束 (测试 / docs PR 边界) | momus audit 是 docs, 接受门槛 = 报告完整性 (10 gap + 修正) | ✅ (G1 修后) |
| 5 强约束 (H/M 风险 rollback) | 全部 L 风险, rollback 是 nice-to-have | ✅ (G1 修后) |
| 5 强约束 (顺序锁死) | A→B→C 收尾, momus 复审是 docs PR (跨阶段元工作) | ✅ |
| 5 强约束 (量化 KPI) | 10 gap + 4 修 + 1 索引 + 3 plan 改 = 18 KPI | ✅ |

## 6. 未在本 PR 范围 (推后续)

- G5 ship report 模板升级 (0.1d) — 推独立 PR
- G7 防御 check 升级 (0.3d) — 推独立 PR
- G8 ship report 模板加 2 行 (0.1d) — 推独立 PR
- G9/F8 Backend 加 process_* 暴露 (0.2d) — 推独立 PR (F8)
- G10/F18 C1.3 alert rule (0.3d) — 推独立 PR (F18)
- F1-F22 followups 22 项 — 跨多 session 推, 推荐起点 F8+F18

## 7. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` (本 PR 修 3 处 + 1 段)
- 上一站 momus: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` (规划 6 维度初审核)
- 本会话 13 commit: B6 完整 + Playwright + 5 推后 + C1 启动 + C1.2
- 5 强约束: 规划 §7 (本 PR 修 G1 适用边界)
- Out of Scope: 规划 §8
- 推后总索引: `docs/followups.md` (本 PR 创)
- 5 强约束历史教训: 规划 §9 (本会话应用 7 条)

**本 momus audit 结论**: 10 gap 中 5 P0/P1 修 (G1+G2+G3+G4+G6), 5 P1/P2 推后续 PR. 修正后规划 + 实施 = "v2 完整版". 跨多 session 推 followups 22 项, 推荐起点 F8 + F18 (1.5-2d).
