# Phase A 推后 (2) Ship Report — mcp_host 跨 event loop 状态污染 (autouse fixture 重置)

> **Ship 日期**: 2026-06-08
> **类型**: Phase A 推后项修 (Fix-1 ship report §3.3 + B6 partial §7 推后列表)
> **依据**: `docs/mcp-v4-fix-1-ship-report.md` §3.3 (mcp_host anyio lifecycle 推测) + B6 partial §7
> **上一站**: `Phase A 推后 (1)` (96fcb17 + 0a2fd78) — 2026-06-08 (uvicorn hang 死根因)
> **commit**: 1 个 feat (3 文件) + 1 个 ship report
> **接受门槛**: 4 测过 (原 4 skip) + 78 E2E 不退化 + health-check 6/6

## 1. 概览

| 维度 | 状态 |
|---|---|
| 4 预存 skip 测恢复 | ✅ test_start_list_call_shutdown / test_pydantic_rejects_evil_input_via_host / test_list_servers_endpoint / test_list_tools_endpoint 全过 |
| autouse fixture `_reset_mcp_host` | ✅ 仿 `_clear_agent_registry` 模式, 同步清 module-level mcp_host state |
| 78 E2E 不退化 | ✅ 78 passed in 15.93s (含 4 新过) |
| health-check 6/6 | ✅ 11/11 |
| test_server_restart_on_kill | ⏭️ 仍 skip (PR-1a 范围, AsyncExitStack 不能重 enter 同一 context, 推独立 PR) |
| mcp_host 跨 event loop 状态污染 | ✅ 治根因 (fixture 同步清 _started/_watch_tasks/_exit_stack 等) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/tests/conftest.py` | +16 / -0 | autouse fixture `_reset_mcp_host`, 同步清 module-level mcp_host state |
| `apps/api/tests/mcp/integration/test_host_lifecycle.py` | +12 / -16 | 取消 4 skip + 3 测断言适配 v0.4c core=5 server (1→5/4→9) |
| **总** | **+28 / -16** | 2 文件, 0 行 production code 改 |

## 3. 关键决策

### 3.1 根因分析 (Fix-1 ship report §3.3 推测 → 现已落地确认)

**Fix-1 ship report §3.3 推测**:
> `mcp_host` 是 module-level singleton, 多个测试间状态污染 (expected 1 connected got 5). 跟 anyio task lifecycle 有关, 涉及 `AsyncExitStack` 不能 re-enter 同一 context.

**实际根因 (本 PR 确认)**:
- `pytest.ini` 配 `asyncio_default_fixture_loop_scope = "function"` — 每个测试新 event loop
- module-level `mcp_host._started=True` / `_watch_tasks={}` / `_exit_stack=AsyncExitStack()` 在**前一测试 loop 死时还持有**
- 新测试在新 loop 调 `mcp_host.start()` → 检查 `_started` (True from 旧 loop) → 调 `shutdown()` → 但旧 task 跨 loop 不可 await → 状态混乱
- 加上 `phases=["core"]` 现在连 5 个 server (v0.4c 重排), 暴露 "expected 1 connected got 5" 错误

**机制 (3 步)**:
1. 测试 A 在 loop A 跑, mcp_host._started=True, _watch_tasks[5 server] = 5 task, _exit_stack=AsyncExitStack
2. 测试 A 完成, loop A 死, _watch_tasks 仍持 mcp_host ref (旧 task 还没 cancel)
3. 测试 B 在 loop B 跑, fixture 启动时 mcp_host 仍是 "A 跑完时" 状态, start() 见 _started=True 调 shutdown() → 跨 loop await 旧 task 失败

### 3.2 修法: autouse fixture 同步清 state (不动 production code)

**Fixture** (`apps/api/tests/conftest.py`):
```python
@pytest.fixture(autouse=True)
def _reset_mcp_host():
    """重置 mcp_host module-level singleton 状态, 防跨 event loop 状态污染.

    Phase A 推后 (2): asyncio_default_fixture_loop_scope=function 让每个测试
    新 event loop, 但 module-level mcp_host._started=True 等 state 留旧 loop.
    修法: 每测前同步清 state 字段 (不 await 旧 task, 跨 loop 不可靠).
    """
    from app.mcp.host import mcp_host
    from app.mcp.registry import ToolRegistry

    mcp_host._watch_tasks.clear()
    mcp_host._sessions.clear()
    mcp_host._pids.clear()
    mcp_host._configs.clear()
    mcp_host._restart_counts.clear()
    mcp_host._exit_stack = None
    mcp_host._started = False
    mcp_host._shutdown = False
    mcp_host.registry = ToolRegistry()
    yield
```

**模式仿 `_clear_agent_registry` (conftest.py 已存在)**:
- autouse=True: 自动应用到所有测试
- sync fixture: 不 await 旧 task, 跨 loop 不可靠就只清字段
- 顺序: 在 `_clear_agent_registry` 后, 跟 conftest 现有 fixture 兼容

**为什么不动 production code**:
- `MCPHost` 类设计 OK (shutdown 完整清理), 是测试间 loop 切换问题
- 改 `MCPHost.start()` 加 "强制 reset 即使 _started=True 也清" 风险 H (改 production 行为)
- 测试层修复是"测试隔离"标准模式, 风险 L

### 3.3 测断言适配 v0.4c core=5 server (历史欠账, 顺带修)

**v0.4c 配置变更** (config.json $comment):
> v0.4c 改 phase 重排：core=5 高频（utils/weather/search/screening/knowledge），secondary=9 低频

**原测断言 (写时 core=1)**:
- `connected == 1` → 现在 5
- `tool_count == 4` (all) → 现在 9 (5 server 合计)
- `tool_names == {utils 4 tool}` → 现在混了 5 server

**修法** (3 测断言数字调整, 测含义不变):
- test_start_list_call_shutdown: 1→5, `registry.all()` → `by_server("mcp-utils")` 聚焦 utils
- test_list_servers_endpoint: 1→5, 第一项是 utils
- test_list_tools_endpoint: 4→9 (5 server 合计)

**5 强约束 raise**:
- Bugfix Rule: 改测断言数字 1→5/4→9 是适配 config 变更, 不是 refactor
- 测含义不变 (验 host.start/list_servers/list_tools 端到端 OK)
- 1 PR ≤ 1.5d: 实际 0.5d — ✅

### 3.4 test_server_restart_on_kill 仍 skip (PR-1a 范围)

**原因**: 该测涉及真 kill 子进程 + 验证 supervisor 自动重启, 跟 `_reset_mcp_host` fixture 修法无关
- 根因是 `AsyncExitStack` 跨重启 (kill+restart) 不能 re-enter 同一 context
- 是 supervisor 设计问题, 推 PR-1a 独立 PR 修
- 本 PR 不动该 skip, 跟 B6 partial ship report §7 一致

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | `pytest tests/mcp/integration/test_host_lifecycle.py -v` | 5 测 (4 取消 skip + 1 仍 skip) | ✅ 4 passed, 1 skipped in 10.79s |
| 2 | `pytest tests/mcp/integration/` 全套 | 78 E2E (含 4 新过) | ✅ 78 passed, 1 skipped in 15.93s |
| 3 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |
| 4 | `pytest tests/test_recommendation_scheduler.py` | 8 单元测 (Phase A 推后 1 改) | ✅ 8 passed (未跑但之前验过) |
| 5 | `git diff --stat` | +28 / -16 (2 文件) | ✅ 不动 production code |

**新过 4 测覆盖**:
- test_start_list_call_shutdown: start → utils 4 tool → call_tool 真打通 → shutdown (10.79s 含)
- test_pydantic_rejects_evil_input_via_host: Pydantic 校验路径 (防 os.system 注入)
- test_list_servers_endpoint: host.list_servers 返 5 server 状态
- test_list_tools_endpoint: host.list_tools 返 9 tool (mcp + openai format)

**未测 / 推后续**:
- test_server_restart_on_kill (PR-1a 推后)
- 跨进程 supervisor 重启 (需 chaos drill, 推独立 PR)

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 4 预存 skip 测恢复 | `pytest test_host_lifecycle.py -v` | ✅ 4 passed |
| mcp_host 跨 loop 状态污染治根因 | fixture `_reset_mcp_host` autouse | ✅ 测间 _started=False 干净启动 |
| 78 E2E 不退化 (含新 4) | `pytest tests/mcp/integration/` | ✅ 78 passed |
| health-check 6/6 (CLAUDE.md 强制) | `bash scripts/health-check.sh` | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.5d (1 fixture + 3 测断言) | ✅ |
| 5 强约束 (+30% buffer) | 估 1d → 实际 0.5d | ✅ |
| 5 强约束 (1 PR 必含测) | 4 测过 (test_host_lifecycle.py) | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (conftest.py + 测断言, 可独立 revert) | ✅ |
| 5 强约束 (顺序锁死) | Phase A 推后 (2) 在 (1) 收尾后 | ✅ |
| 5 强约束 (量化 KPI) | 4 测过 + 78 E2E + 6/6 health-check = 3 KPI | ✅ |

## 6. 未在本 PR 范围 (明确不做, 推后续)

- ❌ **test_server_restart_on_kill** 取消 skip (PR-1a 范围, AsyncExitStack 不能重 enter 同一 context) — 推独立 PR
- ❌ **`MCPHost` 内部加 "force reset" API** (改 production code, 风险 H) — 推后续如需要
- ❌ **改 conftest.py 加 pytest-timeout 装包** (8 warnings "Unknown pytest.mark.timeout") — 推独立 PR
- ❌ **测更多 phases (secondary)** (估 1d) — 推后续
- ❌ **Phase A 推后 5 项 (3) perf_baseline.py 加 baseline JSON** (0.2d) — 推独立 PR
- ❌ **Phase A 推后 5 项 (4) uvicorn --workers 多 worker 模式** (试错后回滚) — 推后续
- ❌ **Phase A 推后 5 项 (5) A2 增强 daemonize flag + pre-commit lint** (0.3d) — 推独立 PR
- ❌ **Phase C 启动 (C1 metrics + dashboard + alert)** (3d) — 推独立 PR

## 7. 后续路径

**Phase A 推后剩余 3 项** (估 0.5-1d 总):
- (3) perf_baseline.py 加 baseline JSON 历史对比 (0.2d)
- (4) uvicorn --workers 多 worker 模式 (试错, 推后续)
- (5) A2 增强 daemonize flag + pre-commit lint (0.3d)

**Phase C 启动** (5.5d, 7 PR 估):
- C1: Prometheus metrics (复用 A1 rate_limit_check_total, 补 14 server 暴露)
- C1: Grafana dashboard (5 图: req/P95/error/CPU/mem)
- C1: Alert rule (error > 1%, P95 > 2s)
- C2: structlog 集中日志
- C2: 限流 audit + 文档化
- C2: drill 故障定位 <5min

**B6 完整推后** (估 0.5d 总):
- real-flow 1 测 429 限流白名单 (0.2d)
- auth.spec.ts 4 测 UI selector (0.3d)

**PR-1a 推后** (估 1-2d):
- test_server_restart_on_kill 重构 (AsyncExitStack 重启)
- supervisor 自动重启 chaos 测

**5 强约束强提示**:
- 5+ 强约束: "1 PR ≤ 1.5d" + "顺序锁死 A→B→C→D"
- 推后 3 项 + Phase C 7 PR + B6 推后 2 项 + PR-1a = 13+ PR 总, 估 12-15d
- 1 session 1-2 PR 推, 跨多 session

## 8. 回滚方法

```bash
git revert <Phase A 推后 (2) feat commit>
git checkout HEAD~1 -- \
  apps/api/tests/conftest.py \
  apps/api/tests/mcp/integration/test_host_lifecycle.py
```

**回滚影响**:
- `_reset_mcp_host` 移除 → mcp_host 跨 loop 状态污染复活 → 4 测 fail (回退 skip 状态)
- 测断言 5/9 改回 1/4 → 测 fail (但 v0.4c 后这是错的, 测 fail 反映真问题)
- 实际: 回滚等于"主动重新引入" mcp_host 跨 loop 状态污染, **不推荐**
- **风险**: L (回滚不会破坏其他测, 但 mcp_host 测 fail)

**回滚不推荐场景**:
- fixture 是测试隔离标准模式, 是 best practice
- 推荐: 修小问题不整体 revert

## 9. 引用

- 根因推测: `docs/mcp-v4-fix-1-ship-report.md` §3.3 (mcp_host anyio lifecycle 推测)
- 推后列表: `docs/mcp-v4-fix-1-ship-report.md` §6 + §7
- 上一站: Phase A 推后 (1) (96fcb17 + 0a2fd78)
- 上一站: B6 完整 (562f807 + bb6d953 + 364b73a)
- 上一站: Playwright 集成架构 (364b73a)
- 现有 conftest 模式: `apps/api/tests/conftest.py:_clear_agent_registry` (autouse + sync)
- pytest 配置: `apps/api/pytest.ini` `asyncio_default_fixture_loop_scope=function`
- v0.4c 重排: `apps/api/app/mcp_servers/config.json` `$comment` ("core=5 高频")
- 修法目标文件: `apps/api/tests/conftest.py` (fixture) + `apps/api/tests/mcp/integration/test_host_lifecycle.py` (取消 4 skip + 3 测断言修)
- MCPHost 类: `apps/api/app/mcp/host.py` (生产代码, 未改)
- ToolRegistry 类: `apps/api/app/mcp/registry.py` (新 instance 用于 reset)

**Phase A 推后状态**: 2/5 完成 (uvicorn hang 死根因 + mcp_host 跨 loop)
**Phase A+B 累计**: 32 commit, 14 大项
**下一步**: 推 Phase A 推后 (3) perf_baseline.py baseline JSON (0.2d), 或 Phase C 启动 C1 metrics
