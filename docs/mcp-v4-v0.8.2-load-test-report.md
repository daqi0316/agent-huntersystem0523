# v0.8.2 Load Test Report — spawn-kill vs long-running fd/memory 对比

> **报告日期**: 2026-06-07
> **依据**: v0.8.1 ship report §7 (v0.8.2 init sleep 0.5s→3-5s 修 hidden 问题)
> **关键发现**: v0.8.1 "max fd=1 是 init 不够" 假设**错了** — 真因是 stdin=DEVNULL 触发 stdio 协议退出, spawn-kill 0.5s 测的是启动期, 不是 init 不够

## 1. 实验设置

| 维度 | 值 |
|---|---|
| Server 数 | 14 (5 core + 9 secondary) |
| 场景数 | **4** (A 同步 / B 100ms / C 1s + **D long-running 5s**) |
| Trial/场景 | A/B/C = 10, **D = 3** (5s × 14 × 3 = 210s, 控时间) |
| 总实验 | 33 (30 + 3) |
| **新测模式**: long-running | stdin=PIPE 让 server 不退, 5s 后测稳定态 |
| **旧模式**: spawn-kill | stdin=DEVNULL, 0.5s 后测启动期 |
| 进程管理 | subprocess.Popen + psutil.Process |

## 2. 4 场景数字对比 (v0.8.1 修正版)

| 场景 | 模式 | Trials | P95 wall (ms) | avg failed | max RSS (KB) | max FD | mean RSS |
|---|---|---|---|---|---|---|---|
| A_simultaneous | spawn-kill 0.5s | 10 | **551** | 0.0/14 | **75,504** | **1** | ~70,000 |
| B_100ms_stagger | spawn-kill 0.5s | 10 | **1,817** | 0.0/14 | **100,144** | **1** | ~99,000 |
| C_1s_stagger | spawn-kill 0.5s | 10 | **13,515** | 0.0/14 | **100,192** | **1** | ~99,000 |
| **D_long_running_5s** | **stdin=PIPE 5s** | 3 | **5,052** | 0.0/14 | **128,912** | **0** | ~125,000 |
| **33 总** | — | — | — | **0.0/14** | **128,912** | **1** | — |

## 3. 关键发现 (Momus §3.5 P2 终极答案)

### 3.1 v0.8.1 "max fd=1 是 init 不够" 假设错了

**v0.8.1 报告原文**:
> FD 数字 1 是测的伪影: 0.5s 不够 server 完整启动

**v0.8.2 验证** (尝试 init sleep 0.5→3.0s):
- ❌ sleep=3.0s: max rss=**0KB** (server 在 3s 内**已死**, rc=0)
- 真因: `stdin=DEVNULL` 让 stdio server 启动后立刻退出 (无 JSON-RPC 输入可读)
- 0.5s 时 server 还活着 (启动期), 3s 时已死 (stdin EOF → stdio 协议退出)

**v0.8.2 修复方案**: 加 D 场景用 `stdin=PIPE`, server 不退, 5s 后测**真实稳定态**.

### 3.2 D 场景真数字 (long-running 5s)

| 指标 | 数字 | 含义 |
|---|---|---|
| **max RSS** | **128MB** | server 稳定后 128MB (vs spawn-kill 100MB) |
| **max FD** | **0** | server **无额外 file handle** (psutil.open_files()) |
| **网络连接** | **0** | server **无 network connection** (psutil.connections()) |
| **inherit fds** | 3 (stdin/stdout/stderr) | 父进程继承的 pipe |

**含义**:
- MCP stdio server 是**极轻量级进程**: 128MB RSS, 0 额外 fds
- v0.8.1 报告估的 "10-30 fds" **完全错了** — stdio server 不 listen socket, 不连 DB, 不连 Redis/Qdrant
- 所有重资源操作 (DB conn / Redis conn / Qdrant client) 都在**主 API 进程**, 不在 stdio server

### 3.3 spawn-kill vs long-running 对比

| 维度 | spawn-kill (0.5s) | long-running (5s) | 差异 |
|---|---|---|---|
| RSS | 100MB | 128MB | +28MB (稳定后多 28MB) |
| FD | 1 (transient) | 0 (无) | spawn-kill 有瞬间 fd (probably log file) |
| 场景 | 验证 spawn 安全性 | 验证 server 真能跑 | — |

**v0.8.2 结论**: MCP stdio server 资源占用**比预期小**, spawn-kill 测的 100MB RSS 已基本反映稳态, long-running 只多 28MB (Python module cache + lazy import).

## 4. 主目标验证 (Momus §3.1)

- 33 trials × 14 server = 462 lifecycle, **0 失败** ✅
- 3 模式 (spawn-kill A/B/C + long-running D) 全部稳
- 资源数字真实可信: max RSS 128MB/server, max FD 0/server (long-running 模式)

## 5. 与 v0.8 / v0.8.1 对比

| 维度 | v0.8 (stdio_client) | v0.8.1 (Popen+psutil spawn-kill) | v0.8.2 (Popen+psutil spawn-kill + long-running) |
|---|---|---|---|
| 总 trials | 30 | 30 | **33** |
| 失败率 | 0 | 0 | 0 |
| max RSS | 0 (stdio_client bug) | 100MB (spawn-kill) | **128MB (long-running 真实稳定态)** |
| max FD | 0 (stdio_client bug) | 1 (spawn-kill 启动期) | **0 (long-running 真实稳定态)** |
| P95 wall A | 1548ms | 570ms | 551ms |

**v0.8.2 修复 v0.8.1 误判**:
- v0.8.1: "max fd=1 是 init 不够" → 推 v0.8.2 改 sleep
- v0.8.2 验证: 改 sleep → server 死了, 真因是 stdin EOF, 不是 init
- v0.8.2 修法: 加 long-running 场景, 用 stdin=PIPE 测真稳定态
- v0.8.2 结论: 128MB RSS + 0 fd 是 MCP stdio server 真实资源占用

## 6. 决策

✅ **MCP stdio server 资源占用清晰 — 128MB RSS + 0 额外 fd**

**v0.8.2 价值**:
- **推翻 v0.8.1 错误假设** (max fd=1 是 init 不够)
- **真实稳定态数字**: 128MB RSS / 0 fd / 0 connection
- **D 场景可复用**: long-running 测试模式可测其他 stdio 进程

## 7. 后续路径

| 项 | 估时 | 优先级 |
|---|---|---|
| **v1.2**: 测 evaluation + interview scheduling E2E | 1d | 中 |
| **v1.3**: 测 full pipeline orchestrator (需 GraphState 重构) | 1.5d | 低 |
| 健康检查限流 mitigation | 0.2d | 低 (已知 issue) |

## 8. 引用

- v0.8.1 ship report: `docs/mcp-v4-v0.8.1-load-test-report.md` (误判 "max fd=1 是 init 不够")
- v0.8.2 plan: `.omo/plans/followups-momus-review.md` §3 (v0.8.1 follow-up)
- 压测脚本: `scripts/mcp_v4_v0_8_parallel_14_servers.py`
- Momus 修正版: `.omo/plans/v0.7-v1.0-momus-review.md` §3
- psutil 已用: `apps/api/app/mcp/host.py:24`
- MCP server config: `apps/api/app/mcp_servers/config.json` (14 server)
