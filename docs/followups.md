# 推后事项总索引 (Followups)

> **创建日期**: 2026-06-08
> **目的**: 集中所有散落 ship report 的推后项, 方便下次 session 起点直接看 "现在做什么"
> **维护**: 每次 ship PR 后, 如有新推后项, 追加到对应类别
> **审核**: momus audit 2026-06-08 §G6 推荐创建
> **v2 更新**: momus v2 (本会话 40 commit 后) 找 8 新 gap G11-G18, 详见 `docs/mcp-v4-momus-audit-v2-2026-06-08.md`

## 1. 推后总览 (原 22 项 + v2 新增 G11-G18)

| # | 推后项 | 估时 | 优先级 | 引用 |
|---|---|---|---|---|
| F1 | real-flow 1 测 429 限流白名单 | 0.2d | P1 | B6 完整 §6 |
| F2 | auth.spec.ts 4 测 UI selector 修 | 0.3d | P1 | B6 完整 §6 |
| F3 | Playwright 集成架构 root cause 记录 (技术债) | 0.1d | P3 | Playwright 集成 §6.3 |
| F4 | Playwright upstream issue (root cause 治本) | 1d+ | P3 | Playwright 集成 §6.3 |
| F5 | 全 18 spec 跑过 + CI workflow | 0.5d | P2 | Playwright 集成 §6.4 |
| F6 | mcp_host test cleanup (anyio lifecycle 重构) | 0.5-1d | P2 | Fix-1 §6 (Phase A 推后 2) ← **本会话 ship 4 测恢复, 但 mcp_host lifecycle 设计问题待修** |
| F7 | uvicorn --workers 多 worker 模式 (试错后回滚) | 0d | P3 | Fix-1 §6 (Phase A 推后 4) ← **momus G2 推荐: 显式 skip** |
| F8 | Backend 加 `process_cpu_seconds_total` + `process_resident_memory_bytes` 暴露 | 0.2d | P1 | C1.2 §6 ← **本会话新发现** |
| F9 | Phase A 推后 5 A2 增强剩余 (pre-commit 实际 install 需 user) | 0d | P3 | Phase A 推后 5 §3.3 |
| F10 | perf_baseline.py 实际跑 + 归档 baseline JSON (需 user 触发) | 1-2 min | P3 | Phase A 推后 3 §4 |
| F11 | 历史 18+ ship report retro-fit (A6 模板化) | 0.5d | P2 | A6 §6 |
| F12 | CI 集成 lint check (A6 ship 标 manual stage) | 0.3d | P2 | A6 §6 |
| F13 | B5 SQL 升级推后 (Alembic / SQLAlchemy 2.0) | 0.5d | P2 | B5 ship report |
| F14 | A3+A4 fixture FK 修 (B2 推后) | 0.3d | P2 | B2 ship report |
| F15 | PR-1a test_server_restart_on_kill 重构 (AsyncExitStack 重启) | 1-2d | P2 | Fix-1 §6 / B6 partial §7 |
| F16 | Phase D D1 LangGraph POC 失败 → Phase E (momus G3 修) | 1.5-3.5d | P3 | 规划 §5.4 |
| F17 | check_baseline_run.py + check_e2e_run.py (momus G7 推后续) | 0.3d | P2 | momus audit §G7 |
| F18 | C1.3 alert rule (momus G10) | 0.3d | P1 | 规划 §5.3 |
| F19 | C2.1 structlog 集中日志 | 1.5d | P1 | 规划 §5.3 |
| F20 | C2.2 限流 audit + 文档化 | 0.5d | P1 | 规划 §5.3 |
| F21 | C2.3 drill 故障定位 <5min | 1d | P1 | 规划 §5.3 |
| F22 | Phase D 8 PR (D1-D8, 估 15d) | 15d | P3 | 规划 §5.4 |

**总**: 22 项 (F1-F22) + 8 新项 (G11-G18) = 30 项, 估时 ~30d.

## 1.5 v2 新增 (Momus audit v2 找 8 gap) (momus v2 2026-06-08, 估时 ~5d)

| # | 推后项 | 估时 | 优先级 | 引用 |
|---|---|---|---|---|
| G11 | 4 momus 推后续 (G5 ship report 模板升级 0.1d + G7 check_baseline/e2e_run 0.3d + G8 ship report 模板加 2 行 0.1d) | 0.5d | P1 | momus v2 §G11 + momus v1 §G5/G7/G8 |
| G12 | F21 drill 故障定位 <5min (Phase C 唯一剩核心项, C1 收尾 + F19 全栈 100% + F20 audit ship 后必 ship) | 1d | P1 | momus v2 §G12 + 规划 §5.3 |
| G13 | F11-F14 retro-fit 4 项 (A6 retro-fit 18+ ship report 0.5d + CI 集成 lint 0.3d + B5 SQL 升级 0.5d + A3+A4 fixture FK 0.3d) | 1.6d | P1 | momus v2 §G13 + followups F11-F14 |
| G14 | F15 PR-1a test_server_restart_on_kill 重构 (AsyncExitStack 重启 + chaos 测, 拆 2 PR 1.5d 内) | 1-2d | P2 | momus v2 §G14 + Fix-1 §6 + B6 partial §7 |
| G15 | F6 mcp_host anyio lifecycle 设计问题 (4 测已恢复, 但根因未解 — 拆 singleton 为 instance-level 改 MCPHost.create() factory) | 0.5-1d | P2 | momus v2 §G15 + Fix-1 §3.3 + Phase A 推后 2 |
| G16 | B3 retro-fit 触发条件文档化 (Router 改动 > 50 行 OR 灰度比例 > 10% OR 新增 Router 端点 > 3) | 0.1d | P2 | momus v2 §G16 + 规划 §5.2 B3 |
| G17 | Phase D 拆 session 计划文档化 (8 PR 15d 拆 8-10 session, 详见 momus v2 §G17) | 0.1d | P3 | momus v2 §G17 + 规划 §5.4 |
| G18 | 跨 PR KPI 一致性 + 测耗时瓶颈 (无总 dashboard, 78 E2E 16s 可优化) | 0.3-0.5d | P3 | momus v2 §G18 |

**G11-G18 总**: 8 项, 估时 ~5d (G11 0.5 + G12 1 + G13 1.6 + G14 1.5 + G15 0.7 + G16 0.1 + G17 0.1 + G18 0.4).

## 2. 推荐下次 session 起点 (按优先级 + 估时 + 依赖)

**session 1 (1.5-2d)**:
- F8 Backend 加 process_* 暴露 (0.2d, P1, 紧跟 C1.2) ← 治根因 C1.2 proxy
- F18 C1.3 alert rule (0.3d, P1, 紧跟 C1.2) ← C1 收尾
- F1 + F2 B6 完整推后 (0.5d, P1)

**session 2 (1.5-2d)**:
- F19 C2.1 structlog 集中日志 (1.5d, P1)
- F20 C2.2 限流 audit (0.5d, P1)

**session 3 (1d)**:
- F21 C2.3 drill 故障定位 (1d, P1)
- C 阶段收尾 (4 PR 总 3.5d)

**session 4-5 (3-5d)**:
- F11 + F12 + F13 + F14 (A 推后 retro-fit 1.5d, P2)
- F17 防御 check 升级 (0.3d, P2)
- F15 PR-1a test_server_restart_on_kill (1-2d, P2)

**session 6+ (远期 15d)**:
- F22 Phase D 8 PR (D1-D8, 估 15d)

## 3. 引用

- momus audit: `docs/mcp-v4-momus-audit-2026-06-08.md` (G6 推荐创建本索引)
- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` (4 阶段 17 项 + 推后 5 项)
- 5 强约束: 规划 §7
- 推后列来源: 6+ ship report (B6 完整 / B6 partial / Fix-1 / A6 / B1-B5 / 本会话 Phase A 推后 1-5 + Phase C C1 启动 + C1.2)

**下次 session 起点**: F8 (Backend 加 process_*) + F18 (C1.3 alert), 1.5-2d 估时, 1 PR ≤ 1.5d 内 ship 2 PR.
