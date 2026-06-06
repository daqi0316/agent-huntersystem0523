# ADR 0007: MCP v4 Supervisor 架构

> **状态**: Accepted (待 PR-8 Day 1 实施验证)
> **日期**: 2026-06-06
> **作者**: PR-8 Day 0
> **取代**: 无（首版 supervisor 决策）
> **关联**: `.omo/plans/mcp-v4-pr8-supervisor-pilot-v0.2.md` §2

## Context

v4 MCP 实施（PR-0~7）后，现状：
- `mcp/host.py` 用 `AsyncExitStack` 持有所有 `stdio_client` context
- `mcp/supervisor.py` 文件已存在（含 spawn / watchdog / restart），**但 host 没接**——supervisor 和 host 是两套独立生命周期管理
- `mcp_servers/builtin/utils_server.py` 跑通 1 个 server（mcp-utils，4 工具）
- `mcp_servers/config.json` 只配 1 条

**核心问题**：
1. AsyncExitStack 不能 re-enter 同一 context（v4 impl report §2.3）→ 进程死了无法重启
2. 当前 1 server 限制下不暴露问题；PR-8 要拆 24 工具为多 server，必须先答 supervisor 怎么"真重启"

## Decision

### D1 (P0): 重启策略 — **close-then-respawn**（同 stack 内）

**决定**: supervisor 负责 `subprocess.Popen` 生命周期；session 跟着 process 走；supervisor 决定何时 kill → respawn → host 重建 session。

**否决备选**（B 整 stack 重建）：
- 太重：杀掉所有 server session 只为重启 1 个
- 增加 supervisor 复杂度（需要管"哪些 server 在重建期"）

**实现要点**：
- supervisor 持 `proc` + `restart_count` + `last_exit_code`
- host 持 `session: dict[server_id, ClientSession]`
- supervisor 调 `on_restart` callback → host 关旧 session + 开新 session

### D2 (P0): session 所有权 — **supervisor 先拆**

**决定**: 重启时序：`supervisor.kill(old_proc)` → `host.close_session(server_id)` → `supervisor.spawn(new_proc)` → `host.open_session(server_id)`。

**理由**: supervisor 是 process 生命周期 source of truth，session 是 process 的"客户端视图"，跟着 process 重建。

**否决备选**（B host 先拆）：
- 反直觉（host 是高层）
- 多 session 共用 1 proc 时会有竞态（PR-8 不会但 PR-9 远程 MCP 可能）

### D3 (P0): 冷启动分批 — **3 批 (core/secondary/lazy)**

**决定**（沿用 v3 plan §4.1 + `config.py` 已定义的 `StartupPhase` enum）：
- **core**（启动立即）：用户高频 — calc/greet/time/utils（< 2s 内）
- **secondary**（启动 30s 后）：低频 — candidate/job/search
- **lazy**（首次 call）：极低频 — tavily/jd/skill 装/卸

**理由**: 13+ server 顺序启动 ~5-6.5s 会让首屏卡顿；分批让用户先看到 UI。

**实施**: 已有 `StartupPhase` enum（`config.py:42`），PR-8 Day 1 只需在 `host.py:start()` 调度。

### D4 (P1): 故障检测 — **双轨**（psutil 轮询 + call 失败兜底）

**决定**:
- **轮询**（主）：`psutil` 每 3s 查进程 alive
- **call 失败**（兜底）：`call_tool` 抛 `BrokenPipeError` / `ConnectionResetError` → 标记 dirty → 下次轮询时重启

**理由**: 实战中"慢死"（进程 alive 但 handler hang）只能靠轮询 + call timeout 主动检测；纯懒检测会让"半死"卡用户。

**否决备选**（B 只懒检测）：F-3（网络卡死）会一直 hang，agent 体验崩。

**PR-8 验证**：F-3 故障注入必须在这条决策下通过。

### D5 (P1): 退避 — **指数 + circuit breaker**（PR-8 数据后定）

**暂定**: 1s → 2s → 4s → 8s → 30s cap；1 分钟内 > 5 次重启 → 暂停 5 分钟（circuit open）。

**PR-8 跑出 F-1~F-4 数据后定**（本 ADR §后续工作）。

### D6 (P1): 优雅关停 — **SIGTERM → 5s wait → SIGKILL**

**决定**:
1. `terminate()` 发 SIGTERM
2. 等 5s（`await proc.wait()` with timeout）
3. 5s 内未退出 → `kill()` 发 SIGKILL

**理由**: 长跑 call（如 resume_parser LLM 解析 ~3-5s）需要 in-flight 完成；硬杀会丢数据。

**否决备选**（B 不等）：in-flight call 全部失败 → 用户重试。

**P-8 验证**: F-2（SIGTERM）必须 in-flight 完成且新 session 接 call。

### D7 (P2): 资源上限 — **macOS 暂不设 hard cap**

**决定**（基于 macOS 资源测 `docs/mcp-v4-pr8-macos-resource-test.md`）：
- 实测 5 subprocess × 88MB = 438MB（远低于 512MB RLIMIT_AS）
- **不强制 RLIMIT_AS**（macOS 行为不可靠 + 实测不需要）
- 改为软监控：`memory_watchdog_gb: float = 4.0`（`config.py:91`），超限告警 Sentry

**PR-9 + Linux staging** 重新评估（cgroups 可用）。

## 决策图

```
                    ┌─ supervisor 先拆 (D2)
                    │
call_tool()  ───►  host.call() ─► session.call_tool()
                    │                  │
                    │                  ├─ 成功 → return
                    │                  └─ 异常（BrokenPipe/Timeout）
                    │                       │
                    │                       └► 标记 server_dirty
                    │                              │
                    │       (每 3s 轮询)         │
                    └─ psutil alive? ── 否 ───────┘
                              │
                              ▼
                        supervisor.kill + respawn
                              │
                              ▼
                        on_restart callback
                              │
                              ▼
                        host.close_session + open_session
```

## Consequences

### 正面

- ✅ AsyncExitStack 限制被绕过（supervisor 自己管 proc，host 只管 session）
- ✅ 重启不影响其他 server（隔离）
- ✅ 双轨检测覆盖"硬死" + "慢死"
- ✅ 优雅关停保留 in-flight call

### 负面 / 风险

- ⚠️ 复杂度高：supervisor + host + session 三方协作，需要清晰 callback 接口
- ⚠️ on_restart 时序如果错（旧 session 还引用旧 proc fd）会 leak FD
- ⚠️ 双轨检测在 13+ server 时 3s 轮询 13 个 psutil 调用 = 4 calls/s，开销需测
- ⚠️ macOS RLIMIT_AS 不可靠 → 资源超限靠 Sentry 告警兜底

### 备选方案（已否决）

- **A 备选**: 整个 AsyncExitStack 重建（每次重启杀所有）→ 简单但太重
- **B 备选**: 只用 call 失败懒检测 → 简单但 F-3 hang 检测不到
- **C 备选**: psutil 1s 轮询 → 资源更紧但开销 3x

## Implementation

**PR-8 Day 1**（host.py 改造，0.5d）：
- host.py 注入 `ProcessSupervisor` 实例
- `host.start()` 调 `supervisor.spawn()` 拉 server
- `host.call_tool()` 调 session，异常时通知 supervisor
- `host.shutdown()` 调 `supervisor.shutdown()` 优雅关停

**PR-8 Day 2-3**（4 故障注入，1d）：
- F-1 kill -9：验收 supervisor 在 3s 内拉起新 proc
- F-2 kill -15：验收 in-flight call 完成 + 新 session 接
- F-3 tc delay 30s：验收 5s call timeout 触发 fallback
- F-4 time.sleep(60)：验收 supervisor 10s 内主动 kill + 重启

**PR-8 Day 4**（性能 + 收尾，0.5d）：
- 5 性能预算验收（`v0.2 §5`）
- ship PR-8 → git tag `mcp-v4-pr8`

## 后续工作

- [ ] **D5 退避算法**：PR-8 跑出 F-1~F-4 数据后定（ADR 0007.1）
- [ ] **D7 资源监控**：Linux staging 跑 cgroups 验证（PR-9d）
- [ ] **D8 远程 MCP 复用**：C 轨道远程 server 是否共用 supervisor？（不在 PR-8 范围）

## 引用

- `docs/mcp-v4-impl-report.md` §2.3（AsyncExitStack 限制根因）
- `docs/mcp-v4-pr8-macos-resource-test.md`（§8 资源测）
- `docs/mcp-v4-pr9-tool-inventory.md`（server 拆分粒度）
- `.omo/plans/mcp-v4-pr8-supervisor-pilot-v0.2.md` §2（P0/P1/P2 分级）
- `.omo/plans/mcp-dual-track-refactor.md`（v3 plan 范围更广）
- v4 `apps/api/app/mcp/{host,supervisor,config}.py`（现状）
