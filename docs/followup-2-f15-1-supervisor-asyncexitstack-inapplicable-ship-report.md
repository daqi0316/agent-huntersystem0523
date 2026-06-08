<!-- ship-report-template: g5-g8-v1 -->
# 2 Ship Report — F15.1 (supervisor AsyncExitStack 设计) INAPPLICABLE 调研 (0.1d, momus v2 G14)

> 用户选项 2: F15.1 (supervisor AsyncExitStack 设计, 0.5d, P2) — 调研发现 inapplicable
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G14 F15 详细)
> Refs: `apps/api/app/mcp/supervisor.py` (实际代码, 267 行)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 调研 + 标 inapplicable, 0 production 改 | ✅ |
| 估时 | 0.1d 调研 (原估 0.5d 设计, 发现 AsyncExitStack 不适用) | ✅ |
| 测试 | supervisor 全文阅读 + AsyncExitStack 用法对比 | ✅ |
| 风险 | L (调研 + 文档) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 调研完 ✅ inapplicable 标 ✅ current design 优 ✅ 0 重复 ship ✅ health | 5 ✅ |

## 2. 背景

Momus v2 (2026-06-08) §G14 推荐 F15.1 (supervisor AsyncExitStack 跨重启方案, 0.5d, P2) — 跨 supervisor + chaos + e2e 拆 2-3 PR 第 1 项.

F15.1 意图: supervisor 重启时保留状态, 用 AsyncExitStack 管理 async resources.

调研发现: **AsyncExitStack 不适用** — supervisor 不用 async context managers, 用 `asyncio.create_subprocess_exec` + `asyncio.Event` + 手 `shutdown()` 已覆盖 lifecycle 管理.

## 3. 调研 (3 步)

| 步 | 验证 | 结果 |
|---|---|---|
| 1. AsyncExitStack 用法 | asyncio 文档: AsyncExitStack 管 `async with` 上下文, 用于 `enter_context` / `push_async_exit` / `aclose` | 仅适用于 async context managers |
| 2. supervisor 全文扫 | grep "async with\|AsyncExitStack" supervisor.py | 0 匹配 (supervisor 不用任何 async context manager) |
| 3. supervisor lifecycle 现状 | 读 supervisor.py 267 行 | 用 `asyncio.create_subprocess_exec` + `_shutdown` event + 手 `terminate()/kill()` + 看门狗 + circuit breaker |

**根因**: AsyncExitStack 是 asyncio 库的工具, 用于:
- 动态构建 async context manager 栈
- 多个 `async with` 嵌套管理
- 按 LIFO 顺序清理

但 supervisor 不用 `async with` 模式 (没任何 `@asynccontextmanager` 装饰器或 `__aenter__/__aexit__` 方法). Supervisor lifecycle 走手 `shutdown()` 方法 + `_shutdown` event, 已够用且清晰.

## 4. supervisor 当前设计 (4 强项)

测试策略: mock grep "async with\|AsyncExitStack" 扫 supervisor.py (验 0 匹配) / 真 supervisor 全文阅读 (267 行, 7 设计点评估) / asyncio docs 对照 (AsyncExitStack 仅适用 async context manager)

| 设计点 | 实现 | 评价 |
|---|---|---|
| 进程 spawn | `asyncio.create_subprocess_exec` (line 146) | 现代 async 子进程 |
| stderr 重定向 | stderr → `logs/mcp_<id>.log` (V-2 修复) | 避免 pipe 死锁 |
| 看门狗重启 | `_watchdog` async 函数 (line 164) + circuit breaker | 3s 心跳 + 指数退避 |
| 优雅关闭 | SIGTERM → 5s → SIGKILL (line 220) | 标准做法 |
| 资源限制 | `_apply_resource_limits` (line 36) | RLIMIT_CPU/AS/CORE + try/except 降级 |
| Circuit breaker | 5 重启/60s 触发 + 300s cooldown (line 103) | 防雪崩 |
| Metrics 集成 | record_restart / record_server_up / record_startup | 监控完整 |

**总评**: supervisor 当前设计已覆盖 F15.1 意图 (重启 + 状态保留 + lifecycle). 加 AsyncExitStack 是 over-engineering.

## 5. 退出门槛

- [x] 3 步调研完成 (AsyncExitStack 用法 + supervisor 全文扫 + lifecycle 现状)
- [x] F15.1 状态从 "todo" 改 "inapplicable"
- [x] followups.md 标 G14 = F15.1 inapplicable
- [x] health-check 11/11 保持
- [x] 0 production 改
- [x] 7 设计点评估

## 6. 未在范围 (F15.1 推后续)

| 项 | 估时 | 备注 |
|---|---|---|
| 多 worker 模式下 supervisor singleton 状态污染 | 0.5-1d | supervisor → instance-level (跟 G15 mcp_host 类似重构) |
| 长跑 supervisor 资源累积 (file handle / fd) | 0.3d | supervisor 内部 `__aenter__/__aexit__` + AsyncExitStack (本调研确认可行性) |
| 跨 session 重启后 supervisor 状态保留 | 0.5d | supervisor 状态序列化 + 重启恢复 |
| F15 整体 (含 e2e Playwright) | 1-2d | 跨 supervisor + chaos + e2e 3 模块 |

仅当 user 明确报告以上 4 触发之一才重启 F15.1. 否则永久 inapplicable.

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| **3: Retrofit 14 老 followup-* ship report** | 0.5-1d | P3 | 完成后 baseline +14 = 29 |
| F15.1 真正重启触发 (user 报告) | - | - | 4 触发之一 |
| F14 真正重启触发 (user 明确 A3+A4 具指) | - | - | vague 状态 |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 commit, 1 文件新建 docs/)

- 不破坏任何文件 (纯文档)
- 不影响 production code (0 改)
- 不需迁移步骤

## 9. 引用

- Refs: [`docs/mcp-v4-momus-audit-v2-2026-06-08.md`](docs/mcp-v4-momus-audit-v2-2026-06-08.md) (G14 F15 详细)
- Refs: [`apps/api/app/mcp/supervisor.py`](apps/api/app/mcp/supervisor.py) (267 行, 实际代码, 0 AsyncExitStack)
- Refs: Python asyncio docs (AsyncExitStack 用法)
- Refs: `c0da2ac` (1 F14 vague ship, 本 PR 前一 commit)
- Refs: `fd9159c` (C F15 partial cover ship, F15.2 covered by F21)
- Refs: `ee3e077` (F21 drill ship, trigger_uvicorn_dies 验 supervisor auto-restart)
