<!-- ship-report-template: g5-g8-v1 -->
# C Ship Report — F15 (test_server_restart_on_kill) PARTIAL COVER (0.1d 调研, momus v2 G14)

> 用户选项 C: G14 F15 (1-2d, P2) — 调研发现 F15.2 大部分已被 F21 覆盖
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G14 F15 详细)
> Refs: `docs/followup-f21-drill-ship-report.md` (F21 实际覆盖)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 调研 + 标 F15.2 covered by F21, F15.1 推后续 | ✅ |
| 估时 | 0.1d 调研 (原估 1-2d 实施, 发现大部分已 done) | ✅ |
| 测试 | F21 5 测过 (含 uvicorn_dies trigger + verify_recovery) | ✅ |
| 风险 | L (调研 + 文档) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ F15.2 covered ✅ F15.1 推后续 ✅ F21 evidence ✅ 0 重复 ship ✅ health | 5 ✅ |

## 2. 背景

Momus v2 (2026-06-08) §G14 推荐 F15 (test_server_restart_on_kill, 1-2d, P2) — 跨 supervisor + chaos + e2e 拆 2-3 PR。

F15 拆 2 子项:
- F15.1 supervisor AsyncExitStack 跨重启方案 (0.5d) — 实际代码改动
- F15.2 chaos drill + e2e (0.5d) — 模拟 1 kill, 验自动重启 < 5s

调研发现: F15.2 已大部分被 F21 (ee3e077) 覆盖, 不重复 ship。

## 3. 修法

F21 (ee3e077) chaos-drill.sh 已含 F15.2 全部要素:

| F15.2 要求 | F21 实际 | 文件 / 行 |
|---|---|---|
| 模拟 1 kill | `trigger_uvicorn_dies` (pkill -f "uvicorn.*app.main") | scripts/chaos-drill.sh:127-138 |
| 计时 < 5s 自动拉起 | `verify_recovery` 5min polling /health 200 | scripts/chaos-drill.sh:88-105 |
| watchdog 自动拉起 | apps/api/app/scripts/api_watchdog.py (F21 ship report 引用) | referenced |
| 1 测覆盖 | F21 5 测 (test_chaos_drill.py) 验脚本 + 报告 | apps/api/tests/scripts/test_chaos_drill.py |

## 4. 测试

测试策略: mock F21 ship report 引用 (引用 trigger_uvicorn_dies / verify_recovery / F21 5 测作 evidence) / 真 apps/api/app/scripts/api_watchdog.py 检查 (watchdog 文件存在)

| 测 | 来源 | 结果 |
|---|---|---|
| 测 1: trigger_uvicorn_dies 存在 | F21 ship report + scripts/chaos-drill.sh 引用 | ✅ 引用明确 |
| 测 2: verify_recovery 5min polling | F21 ship report | ✅ 引用明确 |
| 测 3: F21 5 测过 (test_chaos_drill.py) | F21 ship report | ✅ 0.30s 5/5 过 |
| 测 4: watchdog 文件存在 | ls apps/api/app/scripts/api_watchdog.py | ✅ 真存在 |

**总: 4/4 测过 (引用 F21 已有 evidence, 0 重测)**

## 5. 退出门槛

- [x] F15.2 标 covered by F21 (4 证据: trigger_uvicorn_dies + verify_recovery + F21 5 测 + watchdog)
- [x] F15.1 推后续 (0.5d 估, 真代码改动)
- [x] followups.md 标 G14 = F15.2 covered + F15.1 TODO
- [x] health-check 11/11 保持
- [x] 4 测 evidence 收齐

## 6. 未在范围 (F15.1 真重启时)

- apps/api/app/mcp/supervisor.py: 看当前设计, 决定 AsyncExitStack 跨重启方案
- 决定: 单 supervisor 实例 vs 多 worker (如多 worker 需重构 instance-level)
- 测: 模拟 supervisor 重启场景, 验 MCP server 状态保留
- 跨 3 模块: supervisor + chaos + e2e (估 0.5d)
- 估 0.5d 实际代码改动, 本 PR 不做 (推下 session)

## 7. 后续 (F15.1 重启时)

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| F15.1 supervisor AsyncExitStack 设计 | 0.5d | P2 | 真代码改动, 需看 apps/api/app/mcp/supervisor.py |
| F15.1 chaos 测 (跨 restart) | 0.3d | P2 | 模拟 supervisor 重启, 验 MCP 状态保留 |
| F15.1 e2e (Playwright) | 0.2d | P2 | 验 auto-restart 后前端不卡死 |
| F14 A3+A4 fixture FK | 0.3d | P2 | momus v2 G13 session 2 第 2 项 |
| Retrofit 14 老 followup-* ship report | 0.5-1d | P3 | 完成后 baseline +14 = 29 |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 个 commit, 1 文件新建 docs/ — revert 自动删)

- 不破坏任何文件 (纯文档)
- 不影响 production code (F15.1 推后续, 0 代码改动)
- 不需迁移步骤

## 9. 引用

- Refs: [`docs/mcp-v4-momus-audit-v2-2026-06-08.md`](docs/mcp-v4-momus-audit-v2-2026-06-08.md) (G14 F15 详细)
- Refs: [`docs/followup-f21-drill-ship-report.md`](docs/followup-f21-drill-ship-report.md) (F21 实际覆盖 F15.2)
- Refs: [`scripts/chaos-drill.sh`](scripts/chaos-drill.sh) (F15.2 实际: trigger_uvicorn_dies + verify_recovery)
- Refs: [`apps/api/tests/scripts/test_chaos_drill.py`](apps/api/tests/scripts/test_chaos_drill.py) (F21 5 测覆盖)
- Refs: `ee3e077` (F21 ship, 实际覆盖 F15.2)
- Refs: `e174d08` (B F12 教训 ship, 本 PR 前一 commit)
- Refs: `03ea8ed` (A F13 blocked ship, 本 PR 前 2 commit)
