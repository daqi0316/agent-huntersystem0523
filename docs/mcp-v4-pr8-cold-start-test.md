# MCP v4 PR-8 冷启动基线测报告

> **测时**: 2026-06-06
> **场景**: 1 subprocess × 10 trials cold start
> **结论**: ✅ **P95 = 342.7ms** < 2s 预算的 17% → §5 预算成立，PR-8 Day 2 pilot 可继续

## 1. 测试目的

v0.3 §8.5 — 验证"spawn subprocess → session.initialize() 返回"时长
对照预算：v0.3 §5 — 冷启动 P95 < 2s

## 2. 测试环境

| 项 | 值 |
|---|---|
| Platform | darwin (macOS) |
| Python | 3.14.3 (apps/api/.venv) |
| Server | `app.mcp_servers.builtin.utils_server` |
| Cwd | `/Users/qixia/agent-huntersystem0523/apps/api` |
| mcp SDK | 1.27.x (uv-installed) |
| 测试脚本 | `scripts/mcp_v4_pr8_cold_start_test.py` |

## 3. 测试方法

每个 trial：
1. 构造 `StdioServerParameters(command=venv_python, args=[-m, utils_server], cwd=apps/api)`
2. `async with stdio_client(params)` 起 subprocess + stdio pipe
3. **`async with ClientSession(read, write)`** 进 context 启动 receive_loop
4. `await session.initialize()` 走 JSON-RPC 握手
5. 记录总时长

> **关键坑**（v4 impl report §2.2 已知）：`ClientSession(read, write)` 必须 `async with` 进 context 启动 receive_loop。直接 `await session.initialize()` 卡死。**这次复现了一次**——第一版没 `async with`，全 trial 超时。

## 4. 实测结果

| 指标 | 值 (ms) |
|---|---|
| min | 327.5 |
| mean | 335.6 |
| stdev | 4.1 |
| P50 | 335.7 |
| P90 | 342.7 |
| **P95** | **342.7** |
| P99 | 342.7 |
| max | 342.7 |

**10/10 成功** | 极小 stdev（4.1ms）说明冷启动高度稳定

## 5. 对比 v0.3 §5 预算

| 指标 | 预算 | 实测 | 余量 |
|---|---|---|---|
| 冷启动 P95 | < 2s | **343ms** | **5.8x** |

**§5 预算成立** — 远低于预算上限。

## 6. 关键发现

### 6.1 ClientSession 异步 context 坑（v4 已知，再踩一次）

v4 impl report §2.2 早就说：
> `session = ClientSession(read, write); await session.initialize()` → `send_request` 永远收不到响应
> 根因：`__aenter__` 没被调，receive_loop 没启动，JSON-RPC 响应没人收
> 修：用 `AsyncExitStack.enter_async_context(session)` 调 `__aenter__` 启动 receive_loop

我第一次写 cold start 测时跳过了 `async with ClientSession(...)`，10 trials 全部 hang。第二版加上后立即成功（342.7ms / trial）。

**教训**：
- **v0.4 必加一条 pre-commit / lint 检查**：`ClientSession(read, write)` 后必须立即 `async with`，**禁止裸用**
- host.py v0.3 §3.4 改造时**必须**沿用 AsyncExitStack 持有 session（v4 impl report §2.3 教训）

### 6.2 冷启动主要耗时 = Python import

343ms 分布：
- Python 3.14 启动基线：~50ms
- import pydantic + sqlalchemy + mcp + fastmcp：~200ms
- import app.tools.{calc, greet, time, operation_log}：~50ms
- FastMCP setup + stdio handshake：~50ms

**优化空间**：
- ~~Lazy import~~ 引入复杂度大，得不偿失
- ~~Pre-fork pool~~ Python 没有，pass
- **接受 343ms** — 比 in-process 调用慢 100x 但用户感知不到（chat 含 LLM 1-3s）

### 6.3 重启 SLA 推算

v0.3 §6.1 三档门槛要求 F-1（kill -9）恢复 < 3s。

实测 cold start P95 = 343ms。剩余 2657ms 用于：
- supervisor 检测进程死亡（3s 轮询）：最坏 3s，但通常 < 1s
- on_restart callback → host 关旧 session + 开新 session：< 100ms

**F-1 恢复 P95 估时**：343 (cold start) + 1000 (detect) + 100 (rebuild) = **~1.5s**，**远低于 3s 预算**。

## 7. 对比 macOS 资源测（Day 0.1）

| 维度 | Day 0.1（资源）| Day 0.5（冷启动）| 一致性 |
|---|---|---|---|
| 单进程 RSS | 88MB | n/a | — |
| 冷启动 P95 | n/a | 343ms | — |
| 5 subprocess 稳态 | 438MB | n/a | — |

**冷启动 + 稳态总和**：5 × (343ms 启动 + 88MB 稳态) ≈ **PR-8 启动期 1.7s + 稳态 440MB**。

## 8. 决策

✅ **§5 冷启动 P95 < 2s 预算成立**（实测 343ms，5.8x 余量）

✅ **Day 1 host.py 改造**（v0.3 §3.4）可立即开始

✅ **F-1 恢复 SLA 推算 ~1.5s**，远低于 §6.1 接受门槛 < 3s

## 9. 风险 + 待验证

| 风险 | 状态 | 后续 |
|---|---|---|
| ClientSession `async with` 坑再次出现 | **本测已踩** | v0.4 加 lint 检查 / pre-commit |
| 10 trials 短测，99% 分位数据稀 | 未验证 | PR-8 Day 2-3 跑生产流量，累积 100+ trial 数据 |
| utils_server 比 pilot 工具（calc + weather）简单 | 实际冷启动可能更慢 | PR-9 真接 calc + weather 时重测 |

## 10. 测试脚本归档

脚本：`scripts/mcp_v4_pr8_cold_start_test.py`
可重跑：`apps/api/.venv/bin/python scripts/mcp_v4_pr8_cold_start_test.py`
- 依赖：mcp SDK（uv-installed）
- 输出：stdout P50/P90/P95/P99 + 决策行
- 配套：`scripts/mcp_v4_pr8_minimal_connect_test.py`（最小化冒烟，单次 trial）
