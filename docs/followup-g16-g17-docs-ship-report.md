# G16 + G17 Docs PR Ship Report

> momus v2 (2026-06-08) §G16 + §G17 文档化 — 0.1d + 0.1d = 0.2d 实际估时
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G16/G17 详细)
> Refs: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2/§5.4 (本 PR 1 行备注源)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| G16 B3 retro-fit 触发条件 doc | 新建 `docs/phase-b-b3-retrofit-触发条件.md` (78 行) — 3 触发条件 + 验收标准 + 监控机制 | ✅ |
| G17 Phase D 拆 session doc | 新建 `docs/phase-d-session-plan.md` (125 行) — 11 session 总览 + 依赖图 + 每 session 估时 | ✅ |
| 0 production code 改 | 纯 docs PR | ✅ |
| 5 强约束 6 维度全列 | 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 / 量化 KPI | ✅ |
| health-check 11/11 | 保持 | ✅ |

Momus v2 审核 v1 (commit 0c2a8fa) G16 + G17 仅在 plan 中以 1 行备注体现, 可读性差且无独立检查清单。本 PR 把 2 触发条件/拆 session 计划升级为独立文档, 含验收标准、监控机制、5 强约束适用。

## 2. 背景

Momus v1 推后续 G16 (B3 retro-fit 触发条件) + G17 (Phase D 拆 session 计划) — 仅 1 行 plan 备注, 可读性差, 后续 contributor 无法快速理解触发条件或拆 session 计划。

## 3. 修法（2 文件新建, 0 production 改）

### 1. `docs/phase-b-b3-retrofit-触发条件.md` (78 行, G16)

**范围**:
- 背景: B3 跳因 (v0.8 Router 30+ E2E 已存在)
- 3 触发条件（任一满足即触发）:
  1. Router 改动 > 50 行（git diff 累计）
  2. 灰度比例 > 10%（featflag 配置 + 监控）
  3. 新增 Router 端点 > 3（git log 累计）
- Retro-fit 实施范围: 1d 估时 / 3-5 测 / 全部 mock LLM
- 验收标准: 触发检测 + 实施 + 测试 + 回归 4 项
- 监控机制: CI 阶段评论 + 发布前脚本 + 季度 review
- 5 强约束: 1.5d / Bugfix Rule / 1 PR 必含测 / 风险 M / 顺序锁死 / 6 KPI

**为何独立 doc 而非 plan 备注**:
- 可被 router 团队/未来 AI agent 直接引用
- 含验收标准, 后续 PR 可对照打勾
- 监控机制（CI 脚本）需要独立 doc 配 `.github/workflows/`
- 季度 review 需要单独 doc 跟踪

### 2. `docs/phase-d-session-plan.md` (125 行, G17)

**范围**:
- 背景: Phase D 16d 远期, 需 8-10 session 拆解
- 11 session 总览（含 D8 例外 2d）:
  - session 1: D7+D5 (1.5d, L)
  - session 2: D3 RLS (1.5d, M)
  - session 3-4: D4 拆 2 session (3d, M)
  - session 5-7: D6 拆 3 session (3d, M)
  - session 8-10: D1+D2 拆 3 session (4d, H)
  - session 11: D8 安全渗透 (2d, H, 例外)
- 每 session: 估时 / 风险 / 依赖 / KPI
- Session 间依赖图: 5 串行链 + 1 独立
- 5 强约束: 11 session / 8 项 / 15d 总 / 0 session 超 1.5d (除 D8)

**为何 11 session 而非 8**:
- D4 拆 2 (cache+批 / 降级+命中率)
- D6 拆 3 (Lighthouse+TTFB / 代码分割 / 图片优化)
- D2 拆 2 (1 流程 / 2-3 流程)
- D8 必单 session（外采跨组织）

## 4. 测试

测试策略: mock 文件存在检查 (用 `ls docs/phase-*.md` 验 2 文件存在) / 真 ship report 自验 (含验收标准 checklist + health 11/11)

- [x] `docs/phase-b-b3-retrofit-触发条件.md` 78 行存在, 3 触发条件明确
- [x] `docs/phase-d-session-plan.md` 125 行存在, 11 session 列出, 依赖图清晰
- [x] 0 production code 改（纯 docs）
- [x] health-check 11/11 保持
- [x] 5 强约束 6 维度全列

## 5. 退出门槛

- 1 PR ≤ 1.5d: 0.2d 实际, docs PR 边界（G1 §7 修后） / +30% buffer
- Bugfix Rule: 0 production 改, docs only
- 1 PR 必含测: docs PR 接受门槛 = 报告完整性 + 5 强约束 6 行 + 引用前后 PR
- 风险 L: docs 改动可独立 revert
- 顺序锁死: G16/G17 在 momus v2 ship (4e99d30) 后, 不破坏 phase 顺序
- KPI: 11 session + 8 项 + 15d + 3 触发 + 1d retro-fit 实施 + 5 强约束 6 行

## 6. 未在范围

- CI 集成 G16 触发检测脚本 (G13 F12 已接部分, G16 完整接入推后续)
- Phase D 8 项实际 ship (按 docs/phase-d-session-plan.md 11 session 计划, 远期)
- 4e99d30 momus v2 ship report (本 PR 引用它, 不重写)

## 7. 后续

- (F retrofit 标 — G16+G17 已 ship, retrofit 14 老 ship report 时同步升级)
- followups.md 总索引 (F1-F22 + G11-G18) 持续维护
- Phase D 远期按 11 session 计划推

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 commit, 1-3 文件新建 docs/ — revert 自动删新建)

- 不破坏任何文件 (纯文档 retrofit)
- 不影响 production code (F 是 docs retrofit, 0 production 改)
- 不需迁移步骤

## 9. 引用

- Refs: [`docs/followups.md`](docs/followups.md) (F1-F22 总索引)
- Refs: [`.omo/plans/2026-06-07-roadmap-corrected.md`](.omo/plans/2026-06-07-roadmap-corrected.md) (修正版规划)
- Refs: [followup-g16-g17-docs-ship-report.md](followup-g16-g17-docs-ship-report.md) (本 ship report)
