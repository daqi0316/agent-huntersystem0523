# Momus Audit v2 Ship Report — 6 维度新状态审核 + 8 新 gap (G11-G18) + 修 3 文件

> **Ship 日期**: 2026-06-08
> **类型**: Momus v2 审核 (替代 v1, 因本会话 40 commit 后状态大改)
> **依据**: 用户请求"替代 momus 做审核, 修正写下来"
> **上一站 momus v1**: `0c2a8fa` (13 commit 后, 找 10 gap G1-G10, 修 4 个)
> **新状态**: 本会话 ship 40 commit 后, 23 PR 累计, Phase C 4.5/6 (F21 drill 唯一剩), Phase D 0/8
> **commit**: 1 docs (3 文件: audit + plan + followups)
> **接受门槛**: 3 文件全修 + 8 新 gap 全列 + health-check 6/6 (11/11)

## 1. 概览

| 维度 | 状态 |
|---|---|
| `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (200+ 行) | ✅ 6 维度 + v1 10 gap 状态更新 + v2 8 新 gap (G11-G18) + 修正建议优先级 |
| `.omo/plans/2026-06-07-roadmap-corrected.md` 3 处 edit | ✅ §5.2 B3 retro-fit 触发条件 (G16) + §5.3 F21 drill 备注 (G12) + §5.4 Phase D 拆 session (G17) |
| `docs/followups.md` 67→83 行 | ✅ 加 §1.5 v2 新增 G11-G18 8 项 + 总数 22→30 项 |
| health-check 11/11 | ✅ (本 PR 纯 docs, 0 production 改) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `docs/mcp-v4-momus-audit-v2-2026-06-08.md` | +200 / -0 | 新建, v1 替代 |
| `.omo/plans/2026-06-07-roadmap-corrected.md` | +20 / -3 | 3 处 edit (G16+G12+G17) |
| `docs/followups.md` | +16 / -0 | §1.5 新增 G11-G18 8 项 + 总数 22→30 |
| **总** | **+236 / -3** | 3 文件, 0 行 production code 改 |

## 3. 关键决策

### 3.1 替代 momus v1 重新审核 (40 commit 后新状态)

**v1 状态 (2026-06-08 13 commit)**: 找 10 gap (G1-G10), 修 4 个 (G1+G2+G3+G4+G6), 推 5 个后续 (G5/G7/G8 推后续 PR + G9 ship as F8 + G10 ship as F18).

**v2 状态 (2026-06-08 40 commit 后)**:
- momus v1 7/10 已修 (G1/G2/G3/G4/G6 + G9 ship as F8 + G10 ship as F18)
- momus v1 3/10 仍待 (G5/G7/G8 → 整合到 v2 G11)
- **v2 新发现 8 gap** (G11-G18) — v1 漏项 + 本会话 ship 引入的新发现

### 3.2 6 维度审核 (v2 新状态)

| 维度 | v2 新发现 |
|---|---|
| 1. 范围完整性 | F21 drill 1d 唯一剩 Phase C 核心项 (G12) + Phase D 拆 plan 缺 (G17) |
| 2. 量化 KPI | 测耗时 16s 累积瓶颈 (G18) + 跨 PR 总 dashboard 缺 (G18) |
| 3. 测试策略 | momus 推后续 4 项 (G5/G7/G8) 0.5d 总没 ship (G11) + F5 全 18 spec CI (G13) + F11/F12 retro-fit 0.8d (G13) |
| 4. 风险 + rollback | Phase D H 风险 PR (D1+D8) 需规划 (G17) |
| 5. 顺序依赖 | F21 1d (G12) + Phase D 拆 plan (G17) + 4 momus 推后续 (G11) |
| 6. 历史教训应用 | 教训 3 (防御 check) 不全 (G7 = G11-2) + 教训 4 (ship report 长度) 递增 (G5 = G11-1) + 教训 6 (测耗时) 瓶颈 (G18) |

### 3.3 8 新 gap (G11-G18) 总览

| Gap | 严重度 | 估时 | 描述 |
|---|---|---|---|
| G11 | P1 | 0.5d | 4 momus 推后续 (G5+G7+G8) |
| G12 | P1 | 1d | F21 drill 唯一剩 Phase C 核心项 |
| G13 | P1 | 1.6d | F11-F14 retro-fit 4 项 (A6+B2+B5) |
| G14 | P2 | 1-2d | F15 PR-1a test_server_restart_on_kill 重构 |
| G15 | P2 | 0.5-1d | F6 mcp_host anyio lifecycle 设计问题 (4 测恢复但根因未解) |
| G16 | P2 | 0.1d | B3 retro-fit 触发条件文档化 |
| G17 | P3 | 0.1d | Phase D 拆 session 计划文档化 |
| G18 | P3 | 0.3-0.5d | 跨 PR KPI + 测耗时瓶颈 |

**总估时**: 5d (G11 0.5 + G12 1 + G13 1.6 + G14 1.5 + G15 0.7 + G16 0.1 + G17 0.1 + G18 0.4)

### 3.4 修 3 文件 (v2 §5 修正应用)

1. **`.omo/plans/2026-06-07-roadmap-corrected.md`** 3 处:
   - §5.2 B3 行加 "retro-fit 触发条件: Router 改动 > 50 行 OR 灰度比例 > 10% OR 新增 Router 端点 > 3" (G16)
   - §5.3 C2 drill 行加 "momus v2 G12: 唯一剩 Phase C 核心项, 必 ship" (G12)
   - §5.4 Phase D 表后加 "拆 session 计划 (8-10 session, 详见 momus v2 §G17)" (G17)

2. **`docs/followups.md`** 1 处:
   - 加 §1.5 "v2 新增 (Momus audit v2 找 8 gap) G11-G18 表" + 总数 22→30 项
   - 更新头注 v2 更新引用

3. **`docs/mcp-v4-momus-audit-v2-2026-06-08.md`** 新建:
   - 200+ 行, 6 维度 + v1 状态对比 + 8 新 gap + 修正优先级 + 修正应用

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | 3 grep 验 plan 3 处 edit 应用 | G16 §5.2 + G12 §5.3 + G17 §5.4 | ✅ 全有 |
| 2 | grep 验 followups G11-G18 8 项 | §1.5 v2 新增表 | ✅ 8 项全有 |
| 3 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |
| 4 | `git diff --stat` | +236 / -3 (3 文件) | ✅ 0 production 改 |

**未测 / 推后续**:
- G11-1/2/3 momus 推后续 4 PR (0.5d 总, 立即可 ship)
- G12 F21 drill 1d (Phase C 收尾, 必 ship)
- G13 F11-F14 retro-fit 4 PR (1.6d, 跨 session 2-3)
- G14-G18 推下 session

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| momus v2 审核 6 维度 | docs/mcp-v4-momus-audit-v2 200+ 行 | ✅ |
| 8 新 gap (G11-G18) 全列 | audit §2 v2 新发现 8 gap | ✅ |
| plan 3 处 edit 应用 | grep G16+G12+G17 | ✅ |
| followups.md G11-G18 8 项 | grep §1.5 表 | ✅ |
| 0 行 production code 改 | git diff 范围仅 docs/ + plan | ✅ |
| health-check 6/6 (CLAUDE.md 强制) | bash scripts/health-check.sh | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.3d (纯 docs) | ✅ |
| 5 强约束 (Bugfix Rule) | 0 existing 改 (纯 docs) | ✅ |
| 5 强约束 (1 PR 必含测) | docs PR (G1 §7 修后: docs 接受门槛 = 报告完整性) | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (docs 改动可独立 revert) | ✅ |
| 5 强约束 (顺序锁死) | 修规划 (不破坏 phase 顺序) | ✅ |
| 5 强约束 (量化 KPI) | 8 新 gap + 3 文件修 + 11/11 health = 15 KPI | ✅ |

## 6. 未在本 PR 范围 (推后续)

- ❌ **G11-1/2/3 momus 推后续 4 PR** (0.5d 总, P1) — 推独立 PR
- ❌ **G12 F21 drill 1d (P1, Phase C 收尾)** — 推独立 PR
- ❌ **G13 F11-F14 retro-fit 4 PR** (1.6d, P1) — 拆 4 PR 跨 session 2-3
- ❌ **G14 F15 PR-1a test_server_restart_on_kill 拆 2 PR** (1-2d, P2) — session 3-4
- ❌ **G15 F6 mcp_host anyio lifecycle 设计修 1 PR** (0.5-1d, P2) — session 3
- ❌ **G16 B3 retro-fit 触发条件 1 docs PR** (0.1d, P2) — session 1
- ❌ **G17 Phase D 拆 session 计划 1 docs PR** (0.1d, P3) — session 1
- ❌ **G18 跨 PR KPI + 测耗时 1-2 PR** (0.3-0.5d, P3) — session 4-5

## 7. 引用

- 替代 momus v1: `docs/mcp-v4-momus-audit-2026-06-08.md` (0c2a8fa, 13 commit 后)
- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` (本 PR 修 3 处)
- followups: `docs/followups.md` (本 PR 加 G11-G18)
- 新建 v2 审核: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (本 PR)
- 本会话 40 commit: `562f807..HEAD` (B6 完整 + 5 推后 + C1 启动 + C1.2 + Momus v1 + F8 + F18 + F1+F2 + F19 全栈 + F20 + F19.1-6 = 23 PR)
- 5 强约束: 规划 §7 (G1 修后: docs PR 接受门槛 = ship report 完整性)

**Momus v2 结论**: 8 新 gap (G11-G18), 3 P1 (G11-1/2 + G12 + G13) 0.3d + 1d + 1.6d 总 2.9d 可立即 ship, 3 P2 (G14/G15/G16) 1.5d, 2 P3 (G17/G18) 0.4d. 总可 ship 4.8d, Phase C 收尾 + momus 推后续 + retro-fit + 远期规划全覆盖.

**下 session 起点** (1.4d 估, 4 PR ship):
1. G16 B3 retro-fit 触发条件 (0.1d, docs, 立即 ship)
2. G17 Phase D 拆 session 计划 (0.1d, docs, 立即 ship)
3. G11-1/3 G5+G8 ship report 模板 (0.2d, 1 PR)
4. G12 F21 drill (1d, 模拟故障 + drill 报告)

总 1.4d 估, 4 PR ship, Phase C 收尾 + momus 推后续 + 远期规划全清.
