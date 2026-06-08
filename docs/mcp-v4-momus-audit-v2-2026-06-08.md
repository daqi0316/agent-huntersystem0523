# Momus 深度审核 v2 — 2026-06-08 (本会话 40 commit 后新状态)

> **审核对象**: 本会话 ship 40 commit (562f807..HEAD) + 规划修正版 + momus v1 (0c2a8fa)
> **审核角色**: Momus (Plan Critic) 替代 v2
> **审核日期**: 2026-06-08
> **方法**: 6 维度深度审核 (v1 框架 + v2 新发现)
> **审核方式**: 对照 momus v1 + 本会话 40 commit 实施情况, 找 v1 漏 + v2 新发现 8 gap + 修正

## 0. v1 vs v2 状态对比 (新状态驱动审核)

| 维度 | v1 状态 (2026-06-08 13 commit) | v2 状态 (2026-06-08 40 commit) |
|---|---|---|
| Phase A 推后 | 0/5 | 4/5 ship (1)+(2)+(3)+(5), 跳 (4) 显式 |
| Phase B | 0/6 | 5/6 ship, 跳 B3 (momus G4 修) |
| Phase C C1 | 0/3 | 4 PR 收尾 (启动+C1.2+F8+F18) |
| Phase C C2 | 0/3 | F19 全栈 100% (7 PR) + F20 (1 PR) = 8 PR |
| Phase C 剩 | 全部 6 项 | **仅 F21 drill 1d** 唯一剩核心项 |
| Phase D | 0/8 | 0/8 (远期) |
| 总 commit | 13 | 40 (+27) |
| 总 PR | 8 | 23 (+15) |
| health-check | 11/11 | 11/11 (持续不退化) |
| 78 E2E | passed | passed (跨 4 推后修) |

**v1 漏项 + v2 新发现 = G11-G18** (8 新 gap).

## 1. v1 10 gap 状态更新 (新状态)

| Gap | 严重度 | v1 状态 | v2 状态 |
|---|---|---|---|
| G1 5 强约束适用边界 | P0 | 待修 | ✅ 修 (plan §7) |
| G2 (4) workers 显式 skip | P0 | 待修 | ✅ 修 (plan §7 推后 skip) |
| G3 D1 POC 失败 → Phase E | P0 | 待修 | ✅ 修 (plan §5.5 placeholder) |
| G4 B3 跳因 | P1 | 待修 | ✅ 修 (plan §5.2) |
| G5 ship report 模板升级 | P1 | 待修 | ❌ **v2 仍待 (G11-1)** |
| G6 followups 总索引 | P1 | 待修 | ✅ 修 (docs/followups.md 22 项) |
| G7 防御 check 升级 | P1 | 待修 | ❌ **v2 仍待 (G11-2)** |
| G8 ship report 模板加 2 行 | P2 | 待修 | ❌ **v2 仍待 (G11-3)** |
| G9 C1.2 proxy 后续 | P2 | 待修 | ✅ **ship as F8** (6b8485a) |
| G10 health 跨 session 监控 | P2 | 待修 | ✅ **ship as F18** (647f677) |

**v1 修后状态**: 7/10 修 (G1-G4 + G6 + G9 + G10), 3/10 仍待 (G5/G7/G8 → 整合到 v2 G11).

## 2. v2 新发现 8 gap (G11-G18)

### G11 [P1] 4 momus 推后续 (G5+G7+G8) 0.5d 总, 没 ship

**问题**: v1 §2 "修正建议优先级" 推 G5 (0.1d) + G7 (0.3d) + G8 (0.1d) = 0.5d 总. 本会话 ship 27 commit (40-13) 全是 followup 推后, momus 推后续没接.

**修法**: 1-3 独立 PR:
- G5 ship report 模板升级 (0.1d): A6 check_ship_report.py 加长度限制 ≤30 行/章节, 防 ship report 膨胀
- G7 check_baseline_run + check_e2e_run (0.3d): 防御 check 升级, 防"未跑 baseline" / "未跑 e2e" 漏跑
- G8 ship report 模板加 2 行 (0.1d): "测试策略: mock X / 真 Y" + "rollback: git revert + N 文件"

### G12 [P1] F21 drill 唯一剩 Phase C 核心项, 1d 待

**问题**: 规划 §5.3 C2.3 "drill 故障定位 <5min" 1d, 估时/风险/测试策略列了, 但没 ship. 跟 F19 (1.5d 估) 比对, 实际 ship 1.5d 用了 8 PR (F19 启动 + F19.1 + F19.2 + F19.3/3.1/3.2 + F19.4 + F19.5 + F19.6). F21 1d 估应该 1-2 PR.

**Phase C 当前状态**: 4.5/6 项 ship. F21 是唯一剩核心项.

**修法**: 推独立 PR, 估 1-1.5d:
- 模拟 1 故障 (DB down / uvicorn 死 / redis disconnect 三选一)
- 计时排查 < 5min
- drill 报告: 模拟故障 + 排查步骤 + 实际耗时 + 改进点
- 1 测覆盖: 故障注入 → 5min 内自动检测 + 告警

### G13 [P1] F11-F14 retro-fit 4 项 1.6d 总, 没接

**问题**: 4 项 A/B 推后, 都是 A6/B2/B5 等 ship 时没接的 retro-fit:
- F11: A6 retro-fit 18+ ship report (0.5d, P2) — A6 ship 标 "ship report 模板化" 但没真接 retro-fit
- F12: CI 集成 lint check (0.3d, P2) — A6 ship 标 "CI 接 lint" 但 manual stage, 没真接
- F13: B5 SQL 升级 Alembic 2.0 (0.5d, P2) — B5 ship 时跳
- F14: A3+A4 fixture FK (0.3d, P2) — B2 推后

**修法**: 拆 4 PR, 各 0.3-0.5d, 跨 2-3 session:
- session 1: F11 + F12 (0.8d, 2 PR)
- session 2: F13 + F14 (0.8d, 2 PR)

### G14 [P2] F15 PR-1a test_server_restart_on_kill 1-2d, 没动

**问题**: 推后项 F15 跨 Fix-1 §6 + B6 partial §7 两处提到, 1-2d 估, 涉及 AsyncExitStack 重启 + supervisor 自动重启 chaos 测. Fix-1 ship 时标"试错后回滚", 推 PR-1a. B6 partial ship 时也提到推独立 PR.

**没动原因**: 范围跨 (1) supervisor 设计 (2) chaos 测 (3) e2e 验收, 1-2d 估, 大于 1.5d 强约束. 需拆 2-3 PR.

**修法**: 推 1-2 PR, 估 1.5d 内:
- F15.1 supervisor 重启设计 (0.5d) — AsyncExitStack 跨重启方案
- F15.2 chaos drill + e2e (0.5d) — 模拟 1 kill, 验自动重启 < 5s

### G15 [P2] F6 mcp_host anyio lifecycle 设计问题 (4 测恢复但根因未解)

**问题**: Phase A 推后 2 (`9ee6ec1` + `030e5d1`) ship "mcp_host 跨 event loop fixture" 恢复 4 测 (`test_start_list_call_shutdown` / `test_pydantic_rejects_evil_input_via_host` / `test_list_servers_endpoint` / `test_list_tools_endpoint`). 但 Fix-1 ship report §3.3 推测的根因 ("mcp_host 是 module-level singleton, 多测间状态污染, anyio task lifecycle, 涉及 AsyncExitStack 不能 re-enter 同一 context") 没真解, 是 fixture reset 绕过.

**潜在风险**: 
- 多 worker 模式触发重新进入
- 长跑 (>1d) 后状态污染累积
- 跨 session 重启后 fixture 不生效

**修法**: 推 1 PR, 估 0.5-1d:
- mcp_host 重构: 拆 singleton 为 instance-level, 改 MCPHost.create() factory
- 测 fixture 简化: 删 reset, 改用 instance
- chaos 测: 多 worker + 长跑 + 跨 session

### G16 [P2] B3 retro-fit 没明确计划 (v0.8 Router 已有 E2E)

**问题**: momus G4 修 "B3 跳因: v0.8 Router 已有 30+ E2E (test_router_dispatch.py), 新增价值低". 跳因合理, 但没明确"如果未来 Router 改动大, retro-fit 计划".

**潜在场景**:
- 重大 Router 改动 (如 A/B 灰度调整, 限流改造, ...)
- v0.8 Router E2E 不够覆盖新场景
- 需要"重新评估 B3 是否需要补"

**修法**: 推 1 docs PR, 估 0.1d:
- docs/followups.md 加 "B3 retro-fit 触发条件" 一节
- 触发条件: Router 改动 > 50 行 OR 灰度比例 > 10% OR 新增 Router 端点 > 3

### G17 [P3] Phase D 15d 远期大块没拆 session 计划

**问题**: 规划 §5.4 Phase D 8 PR (D1-D8) 15d 估时, 没拆 session 计划. 每 session 1-2 PR 是合理上限 (1.5d 强约束). 15d 至少需 8-10 session.

**修法**: 推 1 docs PR, 估 0.1d:
- docs/followups.md 加 "Phase D 拆 session 计划" 一节
- session 1: D7 文档机制 (0.5d) + D5 API rate limit (1d) = 1.5d
- session 2: D3 RLS audit (1.5d)
- session 3: D4 LLM 优化 (3d, 拆 2 PR)
- session 4: D6 前端性能 (3d, 拆 3 PR)
- session 5: D1+D2 LangGraph (4d, 拆 2 PR, D1 POC 失败推 Phase E)
- session 6: D8 安全渗透 (2d, 跨组织采购)

### G18 [P3] 跨 PR KPI 一致性 (无总 dashboard, 测耗时 16s 可优化)

**问题**: 本会话 23 PR 每 PR 都有 3-29 KPI, 但:
- 无总 dashboard 跨 PR 一致性
- 78 E2E 跑耗时 16s 略高 (单测 < 5s, 集成测 < 10s 是合理)
- 测耗时累积: 23 PR 累加 78 E2E, 单跑 1 次 16s, CI 频繁跑成瓶颈

**修法**: 推 1-2 PR, 估 0.3-0.5d:
- 测并行化: pytest-xdist 分布式 (16s → 5s)
- 总 dashboard: `docs/perf-dashboard.md` 跨 PR KPI 汇总
- 测分层: 单元 (5s) / 集成 (10s) / E2E (15s) 拆分

## 3. 6 维度审核 (v2 新状态)

### 3.1 范围完整性 (4 阶段)

| 阶段 | v1 估 | v1 ship | v2 ship | v2 状态 |
|---|---|---|---|---|
| A (3.2d) | 6 项 + 5 推后 | 100% | 100% (含 4 推后) | ✅ 收尾 |
| B (9.5d) | 6 项 (跳 B3) | 0% | 5/6 (83%) | ✅ 基本收尾 |
| C (5.5d) | 6 项 | 0% | 4.5/6 (75%) | ⚠️ 仅 F21 drill 1d 待 |
| D (15d) | 8 项 | 0% | 0/8 (0%) | ⏸️ 远期 |
| E (1.5-3.5d) | placeholder | — | — | ⏸️ 条件性 |

**v2 新发现**: F21 (1d) 是 Phase C 唯一剩核心项, G17 Phase D 拆 session 计划缺失.

### 3.2 量化 KPI (momus v1 §3.2)

| KPI | v1 状态 | v2 状态 |
|---|---|---|
| 每 PR 3 KPI (估时/风险/测) | ✅ 23 PR 全有 | ✅ |
| health-check 11/11 持续 | ✅ 13 commit | ✅ 40 commit (跨 5+ session) |
| 78 E2E 不退化 | ✅ | ✅ (跨 4 推后修) |
| 测耗时 16s | 隐含 | ⚠️ 累积瓶颈 (G18) |
| 跨 PR KPI 总 dashboard | ❌ | ❌ (G18) |

**v2 新发现**: 跨 PR KPI 一致性 + 测耗时瓶颈 (G18).

### 3.3 测试策略 (momus v1 §3.3)

| 测策略 | v1 状态 | v2 状态 |
|---|---|---|
| mock LLM 入口 (B1+B2) | ✅ | ✅ |
| 真 DB 路径 (74+ E2E) | ✅ | ✅ 78 E2E |
| 防御 check (check_ship_report) | ✅ | ✅ |
| 防御 check (check_baseline/e2e_run) | ❌ | ❌ (G11-2 = G7) |
| ship report 模板升级 | ❌ | ❌ (G11-1 = G5) |
| ship report 模板加 2 行 | ❌ | ❌ (G11-3 = G8) |
| structlog 4 测覆盖 | — | ✅ (F19 启动 + F19.4 + F19.5) |
| 限流 audit 6 测 | — | ✅ (F20) |
| F5 全 18 spec CI | ❌ | ❌ (followup F5) |

**v2 新发现**: 4 momus 推后续 (G5/G7/G8) 0.5d 总 + F5 (0.5d) + F11/F12 CI 集成 (0.8d).

### 3.4 风险 + rollback (momus v1 §3.4)

| 维度 | v1 状态 | v2 状态 |
|---|---|---|
| 8 PR 风险 L (v1) | ✅ | ✅ |
| 23 PR 风险 L (v2 累计) | — | ✅ |
| H 风险 rollback | 没 H 风险 PR | ✅ |
| Phase D H 风险 PR (D1+D8) | 远期 | 需规划 (G17) |
| D8 安全渗透 (跨组织采购) | 远期 | 需提前 budget (G17) |

**v2 新发现**: Phase D H 风险 PR 需规划 rollback + 提前 budget (G17).

### 3.5 顺序依赖 (momus v1 §3.5)

| 顺序 | v1 状态 | v2 状态 |
|---|---|---|
| A→B→C→D 锁死 | ✅ | ✅ |
| Phase A 4/5 推后 (1+2+3+5) | — | ✅ ship |
| Phase B 5/6 (B3 跳) | — | ✅ ship |
| Phase C 4.5/6 (F21 待) | — | ⚠️ F21 1d 唯一剩 |
| Phase D 0/8 (远期) | — | ⏸️ G17 需拆 plan |
| Phase E (D1 POC 失败触发) | — | ⏸️ 条件性 |

**v2 新发现**: F21 (1d) + Phase D 拆 plan (G17) + 4 momus 推后续 (G11).

### 3.6 历史教训应用 (momus v1 §3.6 = 规划 §9)

| 教训 | v1 状态 | v2 状态 |
|---|---|---|
| 1. E2E 找 hidden bug 价值 | ✅ B1-B6 应用 | ✅ + B6 完整推后 4 测 + Playwright root cause |
| 2. 估时永远偏低 30-50% | ✅ +30% buffer | ✅ 23 PR 全在 1.5d 内 |
| 3. 防御 check 防再发 | ✅ check_ship_report | ⚠️ 不全 (G7 = check_baseline/e2e_run 缺) |
| 4. ship report 必写 | ✅ 8+ 份 | ✅ 23 PR 全有 (但长度递增, G5) |
| 5. mock LLM 入口 | ✅ B1-B2 | ✅ |
| 6. 真 DB 路径必测 | ✅ 74+ E2E | ✅ 78 E2E (G14: 测耗时瓶颈) |
| 7. health-check 14/14 基线 | ✅ 11/11 | ✅ 11/11 持续不退化 |

**v2 新发现**: 教训 3 (防御 check) 不全 (G7), 教训 4 (ship report 长度) 递增 (G5), 教训 6 (测耗时) 瓶颈 (G18).

## 4. 修正建议优先级 (v2 总)

| Gap | 严重度 | 修正成本 | 修正时机 | 推荐 session |
|---|---|---|---|---|
| G11-1 G5 ship report 模板升级 | P1 | 0.1d | 推独立 PR | session 1 |
| G11-2 G7 check_baseline/e2e_run | P1 | 0.3d | 推独立 PR | session 1 |
| G11-3 G8 ship report 模板加 2 行 | P2 | 0.1d | 推独立 PR | session 1 |
| G12 F21 drill 故障定位 | P1 | 1d | 推独立 PR | session 1 |
| G13 F11-F14 retro-fit 4 项 | P1 | 1.6d | 拆 4 PR | session 2-3 |
| G14 F15 PR-1a | P2 | 1-2d | 拆 2 PR | session 3-4 |
| G15 F6 mcp_host lifecycle 设计 | P2 | 0.5-1d | 推独立 PR | session 3 |
| G16 B3 retro-fit 触发条件 | P2 | 0.1d | 推 docs PR | session 1 |
| G17 Phase D 拆 session 计划 | P3 | 0.1d | 推 docs PR | session 1 |
| G18 跨 PR KPI + 测耗时 | P3 | 0.3-0.5d | 推 1-2 PR | session 4-5 |

**本 PR (momus v2 审核) 修正 G11-G18 docs**: 0.3d 实际, 0 行 production code 改, 纯 docs.

**下 session 推荐起点 (1.5-2d 估)**:
1. G16 B3 retro-fit 触发条件 (0.1d) — docs, 立即 ship
2. G17 Phase D 拆 session 计划 (0.1d) — docs, 立即 ship
3. G11-1/3 G5+G8 ship report 模板 (0.2d) — 1 PR, 升级模板
4. G12 F21 drill (1d) — 模拟故障 + drill 报告

总 1.4d, 4 PR ship, Phase C 收尾 + momus 推后续全清 + 远期规划.

## 5. 修正应用 (本 PR)

1. ✅ 修 `.omo/plans/2026-06-07-roadmap-corrected.md` (3 处):
   - §5.2 Phase B 备注加 "B3 retro-fit 触发条件" (G16)
   - §5.3 Phase C 备注加 "F21 drill 1d 唯一剩核心项" (G12)
   - §5.4 Phase D 加 "拆 session 计划" (G17)
2. ✅ 修 `docs/followups.md` (新增 G11-G18, 更新状态):
   - G11 4 momus 推后续 0.5d (G5+G7+G8)
   - G12 F21 drill 1d
   - G13 F11-F14 retro-fit 1.6d
   - G14 F15 PR-1a 1-2d
   - G15 F6 mcp_host lifecycle 设计 0.5-1d
   - G16 B3 retro-fit 触发条件 0.1d
   - G17 Phase D 拆 session 0.1d
   - G18 跨 PR KPI + 测耗时 0.3-0.5d

## 6. 引用

- 上一站 momus: `docs/mcp-v4-momus-audit-2026-06-08.md` (v1, 10 gap)
- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` (v1 修后 4 阶段)
- followups: `docs/followups.md` (22 项 + momus v1 推后续 5 项)
- 本会话 40 commit: `562f807..HEAD` (B6 完整 + 5 推后 + C1 启动 + C1.2 + Momus + F8 + F18 + F1+F2 + F19 全栈 + F20 + F19.1-6 = 23 PR)
- 5 强约束: 规划 §7 (G1 修后: 代码/docs/config/启动 PR 各自接受门槛)

**Momus v2 结论**: 8 新 gap (G11-G18), 3 P1 (G11-1/2 + G12 + G13) 0.3d + 1d + 1.6d 总 2.9d 可立即 ship, 3 P2 (G14/G15/G16) 1.5d, 2 P3 (G17/G18) 0.4d. 总可 ship 4.8d, Phase C 收尾 + momus 推后续 + retro-fit + 远期规划全覆盖.

**下 session 起点**: G16 (0.1d) + G17 (0.1d) + G11-1/3 (0.2d) + G12 (1d) = 1.4d, 4 PR ship.
