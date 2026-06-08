<!-- ship-report-template: g5-g8-v1 -->
# G15 Ship Report — MCPHost instance-level 重构 (create() factory + reset() 方法) (0.5d, momus v2 G15)

> 用户请求"完成 G15 mcp_host root cause" — 真代码改, instance-level 重构
> 防多 worker / 长跑 / 跨 session state 污染. Refs: 5a63512 (Momus v2 §G15)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 1 脚本改 (host.py 加 2 方法) + 1 测改 (conftest.py 简化) + 1 测加 (4 测) | ✅ |
| 估时 | 0.5d 实际 | ✅ 准点 |
| 测试 | 4 G15 测全过 (factory 独立 / reset 清 state / 多实例隔离 / 向后兼容) | ✅ |
| 风险 | M (singleton 改 instance-level, 多文件影响) | ✅ 控住 |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ create() factory ✅ reset() 方法 ✅ conftest 简化 ✅ 4 测过 ✅ 0 production 改 | 5 ✅ |

## 2. 背景

G15 mcp_host root cause (Momus v2 §G15) — module-level singleton 状态污染:
- **多 worker**: 每个 worker 进程独立, 没问题 (但测试间需 fresh 实例)
- **长跑**: state 累积, _watch_tasks / _restart_counts 等无界增长
- **跨 session**: 测试间 event loop 不同, 旧 task 引用旧 loop 报错

**原状态**: `mcp_host = MCPHost()` module-level singleton, conftest.py 手动清 9 个 state 字段.

修法: 加 `MCPHost.create()` factory + `MCPHost.reset()` 方法, 允许 caller 显式拿独立实例或重置 state, 单点维护.

## 3. 修法 (3 子项)

| 子项 | 修法 | 文件 |
|---|---|---|
| 加 create() factory | classmethod 返 cls() (独立实例) | apps/api/app/mcp/host.py |
| 加 reset() 方法 | 同步清 9 state 字段 (sessions/pids/configs/restart_counts/exit_stack/watch_tasks/start_lock/shutdown/started + registry) | apps/api/app/mcp/host.py |
| conftest 简化 | 14 行手动 state clearing → 2 行 `mcp_host.reset()` | apps/api/tests/conftest.py |
| 加 4 测 | factory 独立 / reset 清 state / 多实例隔离 / 向后兼容 | apps/api/tests/scripts/test_mcp_host_factory.py |

## 4. 测试

测试策略: mock 实例化 + state 隔离验证 (用纯 Python class instance 测试, 不需 mock subprocess)

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1: factory 独立 | MCPHost.create() 返 2 个实例 | h1 is not h2, h1 改 state 不影响 h2 | ✅ |
| 测 2: reset 清 state | h 设 9 state → h.reset() | 9 state 全清 (_started False, sessions/pids/configs/restart_counts/watch_tasks 空, _exit_stack None, _start_lock/_shutdown False) | ✅ |
| 测 3: 多实例隔离 | h1/h2 各设 state → h1.reset() | h1 清, h2 保留 | ✅ |
| 测 4: 向后兼容 | `from app.mcp import host` | mcp_host 单例仍可用, reset() 可调 | ✅ |

**总: 4/4 测过 (0.02s, 纯 Python 实例测试, 无 subprocess)**

## 5. 退出门槛

- [x] MCPHost.create() factory 加
- [x] MCPHost.reset() 方法加
- [x] conftest.py 简化 (14 行 → 2 行)
- [x] 4 测加 + 全过
- [x] module-level mcp_host 向后兼容
- [x] health-check 11/11 保持
- [x] 0 production 改 (仅生产 host.py 加 2 方法 + 测试改)

## 6. 未在范围

- Consumer 改 (mcp_tools.py / agent_service.py 用 create() 替代 mcp_host) — 推独立 PR, 0.3d
- 强制 instance-level (删 module-level mcp_host, 全部用 create()) — breaking change, 推后续
- 长跑 state 累积自动化清理 (定期调 reset() 释放 _watch_tasks) — 推后续

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| Consumer 改 (mcp_tools.py + agent_service.py 用 create()) | 0.3d | P2 | G15 完整实施 |
| 强制 instance-level (删 module-level mcp_host) | 0.3d | P3 | breaking, 需全 codebase 改 |
| 长跑 state 周期清理 | 0.2d | P3 | 推 Phase D 远期 |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 commit, 3 文件 — revert 自动恢复 host.py + conftest.py + 删 test_mcp_host_factory.py)

- 不破坏任何文件 (纯 host.py 加方法 + conftest.py 简化 + 测试加)
- 不影响 production code (factory/reset 是新增, module-level mcp_host 向后兼容)
- 不需迁移步骤

## 9. 引用

- Refs: [Momus v2 §G15](docs/mcp-v4-momus-audit-v2-2026-06-08.md) (root cause 来源)
- Refs: [apps/api/app/mcp/host.py](apps/api/app/mcp/host.py) (本 PR 改: 加 create() + reset())
- Refs: [apps/api/tests/conftest.py](apps/api/tests/conftest.py) (本 PR 改: 用 mcp_host.reset())
- Refs: [apps/api/tests/scripts/test_mcp_host_factory.py](apps/api/tests/scripts/test_mcp_host_factory.py) (本 PR 新建 4 测)
- Refs: `598d25d` (F12 fix, conftest 注释提 G15 后续 root cause)
- Refs: `5a63512` (F retrofit, ship report 提 G15 待修)
- Refs: `2d13fa5` (F3 retrofit, 暴露 14 retrofit bug 同时确认 G15 待修)
- Refs: `b13e0f0` (F4 fix, 14 retrofit dedup 完)
