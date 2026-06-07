# v0.8 Load Test Report — 14 server 并行 spawn 压测

> **报告日期**: 2026-06-07
> **依据**: `.omo/plans/v0.7-v1.0-momus-review.md` §7.4 v0.8 修正版
> **脚本**: `scripts/mcp_v4_v0_8_parallel_14_servers.py`
> **Momus 决策**: 主目标 = **安全验证** (dev 数字 prod 无效, 失败率阈值 0% 必查)

## 1. 实验设置

| 维度 | 值 |
|---|---|
| Server 数 | 14 (5 core + 9 secondary, v0.4c phase 重排后) |
| 场景数 | 3 (A 同步 / B 100ms stagger / C 1s stagger) |
| Trial/场景 | 10 |
| 总实验 | 30 (3 × 10) |
| 总 server lifecycle | 420 (30 × 14) |
| Trial 间 sleep | 0.5s (资源释放, Momus §2.3) |

## 2. 4 关键数字 (Momus 决策 4)

| 场景 | P95 wall (ms) | avg failed/trial | max fd | max rss (KB) |
|---|---|---|---|---|
| A_simultaneous | **1548** | 0.0/14 | 0 ⚠️ | 0 ⚠️ |
| B_100ms_stagger | **2284** | 0.0/14 | 0 ⚠️ | 0 ⚠️ |
| C_1s_stagger | **13647** | 0.0/14 | 0 ⚠️ | 0 ⚠️ |
| **30 总** | — | **0.0/14** | — | — |

**主目标 (Momus §2.1) — 失败率 0%**:
- 总 420 server lifecycle, **0 failed**
- 3 场景 × 10 trial × 14 server 全部成功
- ✅ **14 server 并行不死 — 验证通过**

## 3. ⚠️ fd / memory 数据 = 0 (测量失败, 需 v0.8.1 修)

`max fd` 和 `max rss` 全部为 0 — **不是**系统用了 0 资源, 是**测不到**。

**根因**: `mcp.client.stdio.stdio_client` 用 `anyio` 包装子进程, **不暴露 PID** 给外部代码, `_read_fd_and_rss(pids_collected)` 拿到空 list, 所以 lsof/ps 没目标进程可读。

**修复路径 (推 v0.8.1)**:
- 用 `subprocess.Popen` 直接起 server 进程 (绕开 mcp 库), 拿到 real PID
- 同时 Popen + stdio_client 两套并行 (Popen 用于资源测量, stdio_client 用于 MCP 协议), 互相不影响
- **或**: 接受 mcp 库限制, 改用 `psutil` 库 (Python cross-platform 进程管理, 拿 PID + 资源) — 需加依赖

**v0.8 ship 报告诚实声明**: 主目标 (失败率 0%) 达成, 次目标 (fd/memory 边界) 因 stdio_client 限制未实现, 推 v0.8.1。

## 4. 场景分析

### 场景 A — 同步 spawn (stagger=0)

- **P95 wall = 1548ms**
- 与 v0.4c 5 core 并行 973ms P95 对比: 14 server 比 5 server **多 60%**, P95 **多 60%** (1548 vs 973)
- **线性扩展**: 14/5 = 2.8x server 数 → 1548/973 = 1.59x 时间 (低于线性, 因为 server 启动 I/O 异步)
- 含义: 14 server 并行不会触发 I/O 瓶颈

### 场景 B — 100ms stagger (代码热重载模拟)

- **P95 wall = 2284ms**
- 比场景 A **多 736ms** (1.48x) — stagger 100ms × 13 = 1300ms 理论差, 实际差 736ms (部分 server 启动 < 100ms 完成)
- 含义: 错峰启动不会减少总 wall, 只分散 spike

### 场景 C — 1s stagger (prod 滚动重启模拟)

- **P95 wall = 13647ms**
- 比场景 A **多 12.1s** (8.8x) — stagger 1s × 13 = 13s 理论差, 实际差 12.1s
- 含义: 滚动重启显著拖长 wall, 但**不**是问题 (prod 滚动重启就是 13s+ 量级, 符合预期)

## 5. 与 v0.4e 顺序测对比 (Momus §2.4)

v0.4e 14 server 顺序测数字 (baseline): total 9208ms, P95 898ms/server。

| 维度 | v0.4e 顺序 | v0.8 场景 A 并行 | 倍数 |
|---|---|---|---|
| 总 wall | 9208ms | 1548ms | **6x 快** |
| 失败 | 0 | 0 | — |
| 单 server P95 | 898ms | 110ms (1548/14) | **8x 快** |

**Momus §2.4 评估**:
- v0.4e 顺序 vs v0.8 并行**不可直接对比** (顺序是 sum, 并行是 max)
- 但**总 wall 大幅减少** 9208→1548ms 说明 14 server 并行**比顺序快 6x**
- 实际是 asyncio.gather 的并发优势, 不是 mcp 协议本身

## 6. CI / Docker 兼容性 (Momus §2.2)

- lsof / ps 命令 try/except 包, 缺时返 `fd_measurement = "lsof_na"` / `"ps_na"`
- macOS dev 机器有 lsof/ps, 当前实验**实际拿到 fd/rss=0 是 pids 收集问题** (v0.8.1 修)
- CI / Docker 兼容性: lsof 在 alpine Docker **不**装, 脚本自动降级, 不阻塞

## 7. 决策

✅ **14 server 并行 spawn 安全 — 主目标达成, 失败率 0%**
- 30 实验 × 14 server = 420 lifecycle, **0 失败**
- 3 场景 (同步 / 100ms / 1s stagger) 全部稳定
- 资源边界 (fd/memory) 推 v0.8.1 重做测量 (stdio_client PID 暴露问题)

## 8. 后续路径

**v0.8.1 (0.5d, 1 commit) — fd/memory 真实测量**:
- 用 `subprocess.Popen` 绕开 mcp 库, 拿 real PID
- 或加 `psutil` 依赖 (跨平台进程管理, 拿 PID + RSS + fd)
- 重测 v0.8 30 实验, 出**真实** fd/rss 数字

**v1.0a (0.5d) + v1.0b (0.5d)**: 推 v0.7-v1.0 计划继续

## 9. 引用

- v0.8 plan: `.omo/plans/v0.7-v1.0-momus-review.md` §7.4
- v0.8 Momus 审核: `.omo/plans/v0.7-v1.0-momus-review.md` §2 (5 项 v0.8 问题)
- v0.4e 顺序测: `docs/mcp-v4-v0.4-ship-report.md` §3.5
- v0.4c 5 core 并行: `commit 3626577 perf(mcp): phase 重排` (P95 973ms)
- 压测脚本: `scripts/mcp_v4_v0_8_parallel_14_servers.py`
