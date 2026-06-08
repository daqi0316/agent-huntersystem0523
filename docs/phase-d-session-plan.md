# Phase D 拆 Session 计划

> momus v2 (2026-06-08) §G17 — 0.1d 文档化, 0 production code 改动
> Refs: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.4 (Phase D 总览) + §5.4 拆 session 段

## 背景

Phase D (战略投资, 16d 总估) 含 8 项 (D1-D8) + 1 placeholder (Phase E)。
8 项是**远期**, 不在当前 sprint, 但需要 session 级拆分：

1. **可控**：每 session < 1.5d 边界, 不超 5 强约束
2. **可依赖**：session 间依赖清晰, 可串行
3. **可预算**：每 session 可独立预算/排期

## 拆 Session 总览

| session | 项 | 估时 | 风险 | 依赖 | 主要交付 |
|---|---|---|---|---|---|
| 1 | D7 (0.5d) + D5 (1d) | 1.5d | L | Phase C 完成 | 文档机制 + API rate limit |
| 2 | D3 (1.5d) | 1.5d | M | 无 | RLS audit + 8 隔离 case |
| 3 | D4 part 1 (1.5d) | 1.5d | M | 无 | Redis cache + 批调用 |
| 4 | D4 part 2 (1.5d) | 1.5d | M | session 3 | 降级策略 + 命中率测 |
| 5 | D6 part 1 (1d) | 1d | M | 无 | 前端 Lighthouse 测 + TTFB 优化 |
| 6 | D6 part 2 (1d) | 1d | M | session 5 | 前端代码分割 + 懒加载 |
| 7 | D6 part 3 (1d) | 1d | M | session 6 | 前端图片优化 + 缓存策略 |
| 8 | D1 (1d) | 1d | H | 无 | LangGraph POC 报告 |
| 9 | D2 part 1 (1.5d) | 1.5d | H | session 8 | 3 流程迁 LangGraph 第 1 流程 |
| 10 | D2 part 2 (1.5d) | 1.5d | H | session 9 | 3 流程迁 LangGraph 第 2-3 流程 |
| 11 | D8 (2d) | 2d | H | 需提前 budget | 第三方安全渗透报告 |
| **总计** | — | **15d** (8-10 session 估包含拆 D6/D4/D2, 含 D1 POC 失败余地) | — | — | — |

## Session 详细计划

### session 1: D7 + D5 (1.5d, L 风险)

**理由先做**: 文档机制 (D7) 是后续所有 PR 自动更新 doc 的基础, API rate limit (D5) 是性能基线。

| 子项 | 估时 | 测 | 交付 |
|---|---|---|---|
| D7 文档机制 (1 lint + 1 模板) | 0.5d | 1 测 | 后续 PR 自动更新 doc |
| D5 API rate limit 标准化 (per-endpoint) | 1d | 1 测 | 中间件测, 1 测覆盖 |

**KPI**: doc auto-update 100% / per-endpoint rate limit 全覆盖

### session 2: D3 RLS (1.5d, M 风险)

**理由单 session**: RLS audit + 8 隔离 case 是完整工作单元, 不拆。

| 子项 | 估时 | 测 | 交付 |
|---|---|---|---|
| D3 RLS audit | 1.5d | 8 隔离 case | 1 测覆盖, 报告 1 份 |

**KPI**: 8 隔离 case 全过 / cross-org leak 0

### session 3-4: D4 LLM 优化 (3d, M 风险, 拆 2 session)

**理由拆 2 session**: Redis cache + 批 (session 3) 与降级策略 + 命中率测 (session 4) 是不同关注点, 拆可降低单 session 风险。

| session | 子项 | 估时 | 测 | 交付 |
|---|---|---|---|---|
| 3 | D4-1 Redis cache + 批调用 | 1.5d | 命中率测 | cache 命中 > 60% (基线对比) |
| 4 | D4-2 降级策略 + 命中率验 | 1.5d | 降级路径测 | 成本 -30% (mock 测) |

**KPI**: 成本 -30% / cache 命中 > 60% / 降级路径全覆盖

### session 5-7: D6 前端性能 (3d, M 风险, 拆 3 session)

**理由拆 3 session**: 测 (session 5) + 代码分割 (session 6) + 图片优化 (session 7) 独立。

| session | 子项 | 估时 | 测 | 交付 |
|---|---|---|---|---|
| 5 | D6-1 Lighthouse + TTFB 优化 | 1d | Lighthouse 测 | TTFB -50% (1 关键页) |
| 6 | D6-2 代码分割 + 懒加载 | 1d | bundle size 测 | 首屏 JS -40% |
| 7 | D6-3 图片优化 + 缓存策略 | 1d | LCP 测 | LCP < 2.5s |

**KPI**: TTFB -50% / JS -40% / LCP < 2.5s

### session 8-10: D1+D2 LangGraph (4d, H 风险, 拆 3 session)

**理由拆 3 session**: POC (session 8) 必先做, 失败推 Phase E; 实施拆 2 session 1 流程 + 2 流程。

| session | 子项 | 估时 | 测 | 交付 |
|---|---|---|---|---|
| 8 | D1 LangGraph POC | 1d | 1 流程跑通 | POC 报告 (迁移可行性) |
| 9 | D2-1 第 1 流程迁移 | 1.5d | 迁移前后 E2E | 1 流程走 LangGraph, E2E 不退 |
| 10 | D2-2 第 2-3 流程迁移 | 1.5d | 迁移前后 E2E | 2 流程走 LangGraph, E2E 不退 |

**KPI**: POC 报告 / 3 流程走 LangGraph / E2E 不退化

**注意**: session 8 POC 失败 → 推 Phase E (估 1.5-3.5d, 见 `.omo/plans/2026-06-07-roadmap-corrected.md` §5.5)

### session 11: D8 安全渗透 (2d, H 风险, 需提前 budget)

**理由单 session**: 外采第三方, 跨组织采购流程长, 需**提前 1-2 sprint** 启动 budget 流程。

| 子项 | 估时 | 测 | 交付 |
|---|---|---|---|
| D8 安全渗透测试 | 2d | 第三方执行 | 1 份报告, P0/P1 修复列 |

**KPI**: 1 份第三方报告 / P0 全修 / P1 列 backlog

## Session 间依赖图

```
session 1 (D7+D5)
    │
    ├─ session 2 (D3 RLS)  [独立]
    │
    ├─ session 3 (D4-1) ── session 4 (D4-2)  [串行]
    │
    ├─ session 5 (D6-1) ── session 6 (D6-2) ── session 7 (D6-3)  [串行]
    │
    └─ session 8 (D1 POC) ── session 9 (D2-1) ── session 10 (D2-2)  [串行, POC 失败推 Phase E]

session 11 (D8 安全)  [独立, 需提前 budget]
```

## 5 强约束 适用

- 1 PR ≤ 1.5d: 每 session 估时 ≤ 1.5d (D8 例外 2d, 需 H 风险预算)
- Bugfix Rule: D3/D5/D7 修不重构
- 1 PR 必含测: 每 session 至少 1 测
- 风险 M-H: D1/D2/D8 是 H, 需独立 budget + 跨组织协调
- 顺序锁死: session 3→4 / 5→6→7 / 8→9→10 严格串行
- KPI: 11 session / 8 项 / 15d 总 / 0 session 超 1.5d (除 D8)
