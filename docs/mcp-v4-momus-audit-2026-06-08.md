# Momus 深度审核 — 2026-06-08 复审 (13 commit + 规划修正版)

> **审核对象**: 本会话 ship 13 commit (6 大项: B6 完整 + Playwright 集成架构 + Phase A 推后 1+2+3+5 + Phase C C1 启动 + C1.2) + `.omo/plans/2026-06-07-roadmap-corrected.md` 规划
> **审核角色**: Momus (Plan Critic) 替代
> **审核日期**: 2026-06-08
> **方法**: 6 维度深度审核 (范围完整性 / 量化 KPI / 测试策略 / 风险+rollback / 顺序依赖 / 历史教训应用)
> **审核方式**: 对照前次 Momus review (§0-§4 已审规划) + 本会话 13 commit 实施情况, 找 10 gap + 修正

## 0. 概览

| 维度 | 状态 | 严重度 |
|---|---|---|
| 1. 范围完整性 | ⚠️ 3 gap | G2 (P0) / G3 (P0) / G4 (P1) |
| 2. 量化 KPI | ⚠️ 2 gap | G5 (P1) / G6 (P1) |
| 3. 测试策略 | ⚠️ 1 gap | G1 (P0) + G8 (P2) |
| 4. 风险 + rollback | ✅ OK | 全部 L 风险, rollback 都标 |
| 5. 顺序依赖 | ⚠️ 2 gap | G2 (P0) / G3 (P0) |
| 6. 历史教训应用 | ⚠️ 2 gap | G7 (P1) / G10 (P2) |

**总评**: 6 维度 4 维有 gap, 3 个 P0 + 4 个 P1 + 3 个 P2. 修正后规划 + 实施可重命名为"v2 完整版"。

## 1. 10 Gap 详细 (G1-G10)

### G1 [P0] 5 强约束适用边界未明

**问题**: 5 强约束说"1 PR 必含测", 但本会话 8 PR 中:
- Playwright 集成架构 (`364b73a`): 纯 docs PR, 0 测
- Phase C C1 启动 (`d2e9f38`): 纯 docs PR, 0 测
- Phase A 推后 5 (`55173eb` + `d5ad8e2`): 3 验证 (CLI flag + yaml + lint), 验证不是代码测
- Phase A 推后 3 (`a6b1a77`): 6 单元测覆盖 1 纯函数 (mock data), 不是真 backend 测

**实际**: docs/config/启动 PR 不严格适用"1 PR 必含测"强约束 (因为没 production code 改)

**修正建议**: 在 5 强约束 §7 加适用边界:
```
3. **测试**:
   - 代码 PR: 必含 1+ 测, 测必含 mock LLM / 真 DB 二选一明示
   - docs PR: 接受门槛 = ship report 完整性 (9 章节 + 引用前后 PR)
   - config PR (pre-commit hook, daemonize flag): 接受门槛 = 3 验证 (CLI flag + yaml + lint)
   - 启动 PR (现状记录): 接受门槛 = 现状 curl + grep 验 N 项指标
```

### G2 [P0] Phase A 推后 (4) uvicorn workers "试错后回滚" = 无动作

**问题**: 规划 §6 推后列 (4) "uvicorn --workers 多 worker 模式 (试错后回滚)", 但:
- 没标"试错"具体方案 (怎么试? 1 worker → 2 workers → 4 workers? master 启动时序怎么验?)
- Fix-1 ship report §3.2 已经写过: "试错 --workers 2 后回滚" (2 试 1 错)
- 本会话 4 个 Phase A 推后 ship report 都标 (4) skip, 等于无动作

**实际**: (4) 是"知道问题但不动手", 等于永远 skip

**修正建议**: 显式把 (4) 改成:
- 选项 A: 删除 (4), 4/5 完成即收尾, ship report §7 改 "4/5 完成 (1)(2)(3)(5) ship, (4) 删除 — 试错已在 Fix-1 完成且回滚"
- 选项 B: 保留 (4) 但标"等生产环境触发再试", ship report 加 "生产触发条件: uvicorn 单 worker CPU 饱和 >80% 持续 5min"

**推荐选项 A**: 因为试错已在 Fix-1 完成, 后续生产触发再议

### G3 [P0] Phase D D1 LangGraph POC 失败 → Phase E 范围未定义

**问题**: 规划 §5.4 "D1 POC 失败则推 Phase E", 但 Phase E:
- 范围未定义 (估时 / 风险 / KPI)
- 8 列里 Out of Scope 没标 Phase E
- 引用文档里没 Phase E 占位

**修正建议**: 给 Phase E 加 placeholder:
```
### 5.5 Phase E: LangGraph 替代方案 (如 D1 POC 失败, 估 3-5d)

| 项 | 估时 | 风险 | 测试策略 | 量化 KPI |
|---|---|---|---|---|
| E1: 评估替代方案 (自家 Pipeline 加强 vs 维持) | 1d | M | 决策报告 | 1 份 go/no-go 报告 |
| E2: 维持 + 文档化决策理由 (如 E1 选维持) | 0.5d | L | 文档 | 1 份决策说明 |
| E3: 替代框架 (如 AutoGen / CrewAI) 调研 (如 E1 选替换) | 2d | H | POC 跑 1 流程 | 1 份评估报告 |
| **小计** | **1.5-3.5d** | — | — | — |
```

### G4 [P1] Phase B B3 Router 跳的原因未明

**问题**: 本会话 ship 5/6 Phase B PR, 跳 B3 Router. ship report + 规划都标"跳", 但:
- 没明说"为什么跳" (E2E 价值低? 已 ship?)
- 跳不等于"完成", 留下 hidden bug 风险

**修正建议**: 明确跳因:
```
B3 跳因: v0.8 Router ship (test_router_dispatch.py 已存在, 30+ 测), 跟 Pipeline/Orchestrator 比,
        Router E2E 价值低 (单组件, 1d 估时 vs Pipeline 1.5d / Orchestrator 1.5d).
        如未来 Router 改动大, 补 E2E (推 B3 retro-fit).
```

### G5 [P1] ship report 长度 + 复杂度递增

**问题**: 本会话 8 ship report 长度从 100-150 行 (早期) → 200+ 行 (晚期), 最长 C1 启动 238 行.
- 风险: 越长越难维护, 跟"集中错误代码"反模式
- A6 ship report 说"ship report 模板化 (后续 18 个, 模板化省 30% 时间)", 但本会话 8 ship report 没严格用模板, 自由发挥

**修正建议**: 
- 短期: 本会话 8 ship report 已 ship, 不重写
- 长期: A6 check_ship_report.py 升级, 强制 9 章节 + 限制每章节 ≤30 行 (防 ship report 膨胀)
- 接受: ship report 9 章节 + 引用前后 PR + 5 强约束 6 行, 这些是必填, 自由发挥章节内容允许

### G6 [P1] 推后事项散落多个 ship report, 无总索引

**问题**: 本会话 ship 8 个 ship report + 之前 B6 partial / Fix-1 / A6 / B1-B5 ship report, 推后事项散落:
- B6 完整推后: 4 项 (real-flow 429 / auth UI selector / Playwright root cause / Playwright upstream)
- B6 partial 推后: 集成架构 root cause
- Fix-1 推后: 5 项 (uvicorn hang 根因 / mcp_host / perf_baseline / workers / A2 增强) ← 本会话已 ship 4/5
- A6 推后: 历史 18+ ship report retro-fit / CI 集成 lint
- A3+A4 fixture FK 修 (B2 推后)
- B5 SQL 升级推后
- Phase D D1 POC 失败 fallback
- Phase C C1.2 process_* 暴露 (本会话发现)

**总**: 12+ 推后项散落 6+ ship report, 无总索引

**修正建议**: 创建 `docs/followups.md` 总索引 (本 PR 一并 ship):
- 列 12+ 推后项 + 估时 + 优先级 + 引用 ship report
- 方便下次 session 起点直接看 "现在做什么"

### G7 [P1] 教训应用部分不完整

**问题**: 规划 §9 列 7 条历史教训, 本会话应用情况:
- 教训 1 (E2E 找 hidden bug): B6 完整推后 4 项 (real-flow 429 / auth UI selector / Playwright root cause / Playwright upstream) 没量化"剩余 hidden bug 风险"
- 教训 3 (防御 check): check_ship_report.py 已有 (A 推后 5 接 hook), 但缺防"未跑 baseline" / "未跑 e2e" 的 hook

**修正建议**:
- 短期: ship report §6 "未在本 PR 范围" 列表加 hidden bug 风险评估
- 长期: 推独立 PR 加 `check_baseline_run.py` (验 perf_baseline 跑过) + `check_e2e_run.py` (验 74 E2E 跑过)

### G8 [P2] "5 强约束" 实施不严格

**问题**: 5 强约束 §3 "测必含 mock LLM / 真 DB 二选一明示", 本会话 8 ship report 都隐含在测代码里, 没明示 ship report 模板.
- 5 强约束 §4 "H 风险必有 rollback plan", 全部 8 PR 风险 L, rollback 是 nice-to-have 不是必填

**修正建议**: ship report 模板加 2 行:
```
### 1.x 测试策略
- mock: [是/否 — 什么 mock]
- 真: [是/否 — 什么真 (DB / backend / HTTP)]

### 5.x 风险 + rollback
- 风险: L
- rollback: [git revert + N 文件, 接受门槛 — 不破坏其他测]
```

### G9 [P2] Phase C C1.2 dashboard panel 4+5 用 proxy 而非真指标

**问题**: C1.2 ship report §3.1 改用 `api_request_total` + `python_gc_collections_total` 作 proxy, 因 backend 没暴露 `process_cpu_seconds_total` + `process_resident_memory_bytes`.
- 治根因应是"加 process_* 暴露" (0.2d), 不是"dashboard 用 proxy"
- 短期 proxy 是过渡, 长期应加真指标

**修正建议**: 
- 短期: C1.2 ship report §7 推后续已列 "Backend 加 process_* 暴露 (0.2d)" ✅
- 长期: 下次 session 推 "Backend 加 process_* 暴露" PR, 然后改 C1.2 dashboard 用真指标

### G10 [P2] Backend health 没跨 session 监控

**问题**: 本会话 ship 13 commit, 每次都跑 health-check 11/11 ✅, 但:
- 11/11 是"现在"状态, 没"过去 7 天趋势"
- health-check 退化 (10/11) 时, 没人 alert

**修正建议**: Phase C C1.3 alert rule 推独立 PR, 加 health-check 退化 alert (5min 间隔 cron + 失败 >0 告警).

## 2. 修正建议优先级

| Gap | 严重度 | 修正成本 | 修正时机 |
|---|---|---|---|
| G1 5 强约束适用边界 | P0 | 0.05d (改 §7) | 本 PR (momus audit 顺手) |
| G2 (4) workers 显式 skip | P0 | 0.05d (改 ship report §7) | 本 PR (momus audit 顺手) |
| G3 D1 POC 失败 → Phase E placeholder | P0 | 0.1d (加 §5.5) | 本 PR (momus audit 顺手) |
| G4 B3 跳因明说 | P1 | 0.05d (加 1 行) | 本 PR (momus audit 顺手) |
| G5 ship report 长度 + 模板 | P1 | 0.1d (升级 A6 check_ship_report.py) | 推独立 PR |
| G6 followups 总索引 | P1 | 0.1d (建 docs/followups.md) | 本 PR (momus audit 顺手) |
| G7 教训应用补强 | P1 | 0.3d (加 check_baseline_run.py + check_e2e_run.py) | 推独立 PR |
| G8 ship report 模板加 2 行 | P2 | 0.1d (改 ship report 模板) | 推独立 PR |
| G9 C1.2 proxy 后续 | P2 | 0.2d (加 backend process_* 暴露) | 推独立 PR |
| G10 health 跨 session 监控 | P2 | 0.3d (C1.3 alert 推独立) | 推独立 PR |

**本 PR (momus audit) 修正 G1+G2+G3+G4+G6**: 0.4d 估时, 0 行 production code 改, 纯 docs
**推后续 PR 修正 G5+G7+G8+G9+G10**: 1.0d 总 (5 独立 PR), 跨多 session

## 3. 应用的历史教训 (Momus 视角)

1. **本 momus audit 本身 = 教训 1 (E2E 找 hidden bug) 的 docs 版**: 实施后复审, 找 10 gap, 跟 v1.1 找 v0.4d bug 同理
2. **5 强约束 + 30% buffer 应用**: 本会话 8 PR 实际 0.2-1.3d, 跟 1.5d 限 buffer ~30%
3. **防御 check (G7)**: check_ship_report.py + check_baseline_run.py (推后续) 防再发
4. **ship report 必写 (G5)**: 8 ship report, 但长度 + 复杂度没控 (G5 修正)
5. **mock LLM / 真 DB (G8)**: 测代码隐含, ship report 模板明示 (推后续)
6. **真 DB 路径必测**: 74+ E2E 真 backend, 11/11 health-check 持续不退化
7. **health-check 11/11 是基线**: 每次 ship 后跑, 13 commit 都验过

## 4. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` (前次 Momus 修正版)
- 上一站 momus: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` (规划 6 维度初审核)
- 本会话 13 commit ship (B6 完整 + Playwright + 5 推后 + C1 启动 + C1.2)
- 5 强约束: 规划 §7
- Out of Scope: 规划 §8
- 推后事项散落: 6+ ship report (B6 完整 / B6 partial / Fix-1 / A6 / A1-A6 / B1-B5)

**审核结论**: 10 gap 中 4 P0/P1 在本 PR 顺手修 (G1+G2+G3+G4+G6), 6 gap 推独立 PR 跨多 session (G5+G7+G8+G9+G10). 修正后规划 + 实施 = "v2 完整版", 可重命名.
