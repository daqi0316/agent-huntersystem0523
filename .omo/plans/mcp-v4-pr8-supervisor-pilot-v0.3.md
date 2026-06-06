# MCP v4 PR-8 Supervisor Pilot — v0.3 (Momus 二次审修订版)

> **修订自**: v0.2 + Momus 二次审 6.5/10
> **目标评分**: ≥ 8.0/10
> **修订项**: 3 Critical + 5 Major + 1 Minor（m-1 推到 v0.4）
> **最后更新**: 2026-06-06

## 0. 变更摘要（v0.2 → v0.3）

| 反馈 | 编号 | v0.3 修订 | 落地位置 |
|---|---|---|---|
| 工具盘点 3 个数字自相矛盾 | **C-1** | §2 §15 §16 统一为 **38 工具 / 4 A / 34 B / 0 C** | 同步修 `mcp-v4-pr9-tool-inventory.md` |
| 17 未提交 MCP 文件无归属 | **C-2** | §15 加"PR-7.5 单独 ship 策略" + 范围划分表 | §15.1 |
| Day 1 实施入口未指定 | **C-3** | **新增 §3.4** host.py 4 处修改具体行 | §3.4 |
| F-3 `tc qdisc` 需 sudo | **M-1** | §3.2 F-3 改用 handler hang 机制（与 F-4 合并验证）| §3.2 + §13 |
| 冷启动 P95 没基线 | **M-2** | §8 扩为 "Day 0 + Day 0.5" — Day 0.5 加冷启动基线测 | §8.5 新增 |
| dual-track 验证用例缺 | **M-3** | **新增 §3.5** dual-track pytest 骨架 | §3.5 |
| Day 0 估时 0.5d 实际 1.5d（3x 低估）| **M-4** | §12 全表 ×1.5 重估（4d → 6d）| §12 |
| PR-9 9.5d 没回写 roadmap | **M-5** | §15 加 roadmap 同步任务 | §15.2 |
| ADR D5 退避比 D7 重要 | m-1 | 推到 v0.4（暂不改）| §15.4 |
| v4 lesson → check_mcp_servers.py 任务 | m-2 | §12 Day 2 任务显式加 | §12 |
| health-check.sh 同步 | m-3 | §5 性能预算改用新 health-check 步骤 | §5 |

---

## 1. Goal / Non-Goal

### Goal
1. 验证 supervisor 设计在 AsyncExitStack 限制下能真重启 server（4 种故障全过）
2. 建立 server 拆分模板 — 2 工具迁通后，PR-9 机械复用
3. 5 性能预算达标

### Non-Goal
- ❌ 全 38 工具一次性迁（推到 PR-9）
- ❌ 重写 AsyncExitStack 路径（保留作 PR-8 fallback）
- ❌ 新增远程 MCP server 能力（C 轨道）
- ❌ 改 AB router 算法
- ❌ Type C 流式 / SSE 工具（PR-10+ 单独设计）

---

## 2. 7 个 ADR 问题（P0/P1/P2 分级）

> ADR: `docs/adr/0007-mcp-supervisor.md`（v0.2 Day 0 已 ship，v0.3 不重写）

### P0（PR-8 启动前必须答）

| # | 问题 | 决定 |
|---|---|---|
| **Q1** | 重启策略 | A: close-then-respawn（同 stack）|
| **Q4** | session 所有权 | A: supervisor 先拆（process 是 SoT）|
| **Q6** | 冷启动分批 | A: 3 批（core/secondary/lazy）|

### P1（PR-8 跑出数据后定）

| # | 问题 | 决定 |
|---|---|---|
| **Q2** | 故障检测 | A: 双轨（psutil 3s 轮询 + call 失败兜底）|
| **Q3** | 退避 | TBD（v0.4 优先级提升，m-1）|
| **Q5** | 优雅关停 | A: SIGTERM → 5s wait → SIGKILL |

### P2

| # | 问题 | 决定 |
|---|---|---|
| **Q7** | 资源上限 | 不强制 RLIMIT_AS（macOS 不可靠），改软监控 + Sentry 告警 |

---

## 3. PR-8 Pilot 范围

### 3.1 工具选择（2 个，覆盖 2 条轨道）

| 工具 | 轨道 | 理由 | 不选什么 |
|---|---|---|---|
| **calc** | A (内置) | 纯函数 / 验证基础通路 | — |
| **weather** (skill) | B (skill) | 外部依赖 / 网络故障注入天然场景 | — |

**延后到 PR-9**：candidate（DB+RLS）/ resume_parser（file ref）/ install_skill（admin）/ jd / operation_log

**推到 PR-10+**：dashboard / interview / application / evaluation（service wrapper Type B）

### 3.2 4 种故障注入（M-1 修订：F-3 改 handler hang）

| # | 场景 | 工具 | 验收 | 恢复 SLA |
|---|---|---|---|---|
| **F-1** | `kill -9` 硬杀 | `kill -9 <pid>` | 新 session 自动接 call | < 3s |
| **F-2** | `kill -15` 优雅 | `kill -15 <pid>` | in-flight call 完成，新 session 接 | < 5s |
| **F-3** | 网络卡死（**改用 sleep 模拟，避开 sudo**）| 子进程内 `time.sleep(60)` on read | call 超时降级，进程不死 | call timeout 5s |
| **F-4** | 伪死（stdio pipe 在但 handler hang）| handler `await asyncio.sleep(60)` | supervisor 主动 kill + 重启 | < 10s |

> **M-1 修订理由**：`tc qdisc` 在 macOS 需 sudo，dev 机跑不了。F-3 改用子进程内 sleep 模拟"handler read 卡住"——本质等价（call 不返回），且不需要 root。
>
> **F-3 与 F-4 区别保留**：F-3 = read 卡（call timeout 触发），F-4 = handler 卡（supervisor 主动 kill 触发）。两条路径分别验。

每个故障：
- 1 个 pytest 用例（`tests/mcp/test_supervisor_fault_injection.py`）
- 1 个 Prometheus 指标埋点
- 1 段 ADR 记录观测数据

### 3.3 AB router fallback 策略（dual-track）

```python
# apps/api/app/mcp/host.py: call_tool 流程
async def call_tool(self, name, args):
    try:
        return await self._subprocess_call(name, args)
    except (SubprocessDown, CallTimeout) as e:
        logger.warning("subprocess fallback to in-process: %s", e)
        return await self._inprocess_call(name, args)
```

**验收**：supervisor 整体关闭时，2 工具仍可调（降级模式跑通）——具体 pytest 见 §3.5

### 3.4 Day 1 实施入口（C-3 修订：具体行级修改清单）

host.py 4 处必改：

| # | 位置 | 改动 |
|---|---|---|
| 1 | `host.py:__init__` | 加 `self._supervisor = ProcessSupervisor()` |
| 2 | `host.py:start()` | 替换 `async with stdio_client` 为 `await self._supervisor.spawn(cfg)`；保留 AsyncExitStack 作 fallback 路径 |
| 3 | `host.py:call_tool()` | 加 try/except 走 §3.3 dual-track |
| 4 | `host.py:shutdown()` | 调 `await self._supervisor.shutdown()` 在 exit_stack close 之前 |

新增 import：`from app.mcp.supervisor import ProcessSupervisor`

**不动的部分**（dual-track 保留）：
- `AsyncExitStack` 完整保留（fallback 路径）
- `ToolRegistry` 不变
- `ab_router` 不变

### 3.5 dual-track pytest 骨架（M-3 修订）

```python
# tests/mcp/test_supervisor_dual_track.py

import pytest
from unittest.mock import AsyncMock, patch
from app.mcp.host import MCPHost

@pytest.mark.asyncio
async def test_supervisor_down_fallback_to_inprocess():
    """supervisor 抛 SubprocessDown → 调 calc → 期望 in-process 返 6。"""
    host = MCPHost()

    # Mock subprocess 路径失败
    with patch.object(host, "_subprocess_call", side_effect=SubprocessDown("test")):
        # in-process 路径应被 fallback 调用
        with patch.object(host, "_inprocess_call", return_value="6") as mock_fb:
            result = await host.call_tool("calculate", {"expression": "2*3"})

    assert result == "6"
    mock_fb.assert_called_once_with("calculate", {"expression": "2*3"})

@pytest.mark.asyncio
async def test_supervisor_up_uses_subprocess_path():
    """supervisor 正常 → 走 subprocess 路径。"""
    host = MCPHost()
    with patch.object(host, "_subprocess_call", return_value="6") as mock_sp:
        with patch.object(host, "_inprocess_call") as mock_fb:
            result = await host.call_tool("calculate", {"expression": "2*3"})

    assert result == "6"
    mock_sp.assert_called_once()
    mock_fb.assert_not_called()
```

---

## 4. PR-9 Scale 范围

### 4.1 工具"Type A/B/C"分类（C-1 修订：以 §2 大表为唯一事实源）

| 类型 | 数量 | 范围 |
|---|---|---|
| **A 纯 tool** | 4 | calc / greet / time / docs_search |
| **B service wrapper** | **34**（含 B-light 4 + B-heavy 2）| 其余所有 |
| **C 流式** | 0 | — |
| **总计** | **38 工具** | — |

### 4.2 PR-9 范围定义
- 迁 Type A 4 工具
- 拆 Type B → thin tool wrapper（**不直接迁，要保证 service 走 RLS**）
- Type C 推 PR-10+

---

## 5. 性能预算

| 指标 | 目标 | 测量方法（m-3 修订：同步新 health-check.sh）|
|---|---|---|
| 冷启动 P95 | **< 2s**（PR-8，2 工具）| `bash scripts/health-check.sh` Step 5 + 新增 Step 10（`mcp_server_startup_seconds`）|
| 热调用 P95 | **< 50ms** | `/metrics mcp_call_duration_seconds` |
| 重启 P95 | **< 3s**（F-1）/ < 5s（F-2）| F-1~F-4 注入 + 测 kill→next_call |
| 内存稳态 | **< 2GB**（5 subprocess）| `health-check.sh` Step 10 + `psutil.virtual_memory()` |
| AB router fallback P95 | **< 100ms** | §3.5 dual-track pytest 同测 |

---

## 6. 回滚条件 + 退出标准

### 6.1 三档门槛

| 档位 | 触发 | 动作 |
|---|---|---|
| 接受 | F-1~F-4 全过 + 5 性能预算全达标 | ship PR-8 |
| 重做 supervisor | 任一 F 重启 > 10s **或** 内存 > 4GB **或** 数据丢失 | 回滚 PR-7 + 改 supervisor 设计 |
| 放弃 v4 路线 | AsyncExitStack 限制无解 **或** stdio 性能 < 20 P95 | 锁定 v3 方案 + 关 PR-9 |

### 6.2 回滚方法

- **git tag**: 每 PR ship 前 `git tag mcp-v4-pr8-pre`
- DB schema 不动（PR-8 不改 model），回滚 = 代码回滚
- 失败 → `git checkout mcp-v4-pr8-pre` + 删新 server 目录

---

## 7. 用户体验影响 + 灰度策略

| 阶段 | 配置 | 流量 |
|---|---|---|
| PR-8 ship 前 | `MCP_AB_PERCENT=0` | supervisor 拉起不接流量，in-process 全跑 |
| PR-8 ship 后 24h | `MCP_AB_PERCENT=10` | sticky hash 10% 走 subprocess |
| 观察稳定 | `MCP_AB_PERCENT=50` | 50% |
| 全量 | `MCP_AB_PERCENT=100` | 全 subprocess |

每个 percent 跑 24h 看 Prometheus + Sentry 错误率，无异常再升档。

---

## 8. macOS 资源限制验证（M-2 修订：Day 0 + Day 0.5）

### 8.1 Day 0（已 ship）
- 5 subprocess 稳态 438MB（每个 88MB）
- < 2GB 预算 → 决策点通过

### 8.5 Day 0.5（新增 — 冷启动基线）

**目的**：v0.2 §5 冷启动 < 2s 预算无前置数据，Day 1 前补

**测法**：
```python
# scripts/mcp_v4_pr8_cold_start_test.py
# 1. spawn 1 subprocess 10 次
# 2. 每次测"spawn → session.initialize() 返回"时长
# 3. 取 P95
```

**预期**：P95 < 2s（基于单进程 88MB / 32GB 机器推算）
**预算修正**：如果实测 P95 > 2s，§5 预算松到 < 3s，并在 ADR 0007 D3 标"core 批小工具接受较长冷启动"

---

## 9. Observability 门槛

| 指标 | 状态 | PR-8 补 |
|---|---|---|
| `mcp_calls_total` | ✅ | — |
| `mcp_call_duration_seconds` | ✅ | — |
| `mcp_server_up` | ✅ | alert: < 1 持续 1min → Sentry |
| `mcp_server_restarts_total` | ✅ | alert: > 3/小时 → Sentry |
| `mcp_supervisor_lag_seconds` | ❌ | 新增（kill→reconnect 时长）|
| `mcp_ab_fallback_total` | ❌ | 新增（subprocess 失败 → in-process 兜底）|

---

## 10. CI 守门

- `scripts/check_mcp_servers.py` 已存在（tools / skills / config）
- **PR-8 补**：加 `supervisor_lifecycle` 检查
- pre-commit hook：`bash -c "cd apps/api && .venv/bin/python -m pytest tests/mcp/test_supervisor_lifecycle.py -v"`

---

## 11. 引用 v4 教训（兑现对照表）

| v4 教训 | 本方案如何兑现 |
|---|---|
| AsyncExitStack 跨 task cancel 错 | §3.3 保留 in-process fallback |
| AB router 总是 wrap（PR-1b）| §7 灰度策略延续 |
| register_tool 双用法 bug | §12 Day 2 任务先跑 `check_mcp_servers.py` 验 metadata（m-2 修订）|
| CI 脚本用 venv python | §10 显式 `.venv/bin/python` |
| dead import 破坏 build | PR-8 import 全在 requirements.txt |
| 工具函数当装饰器用 → TOOL_METADATA 空 | §12 Day 2 显式 check（m-2）|

---

## 12. 时间线（M-4 修订：全表 ×1.5 重估）

| Day | 任务 | 估时（原 / 修订）| 验证 |
|---|---|---|---|
| **0** | macOS 资源测 + ADR 起草 + 工具盘点 | 0.5d / **0.75d** | 资源测报告 + ADR + 盘点（已完成 1.5d，超 1.5x）|
| **0.5** | 冷启动基线测（M-2 新增）| — / **0.5d** | spawn × 10 P95 数据 |
| **1** | 改 host.py 接 supervisor（§3.4 4 处）| 1d / **1.5d** | host.py 单元测试 + dual-track pytest §3.5 |
| **2** | pilot calc server + 4 故障 F-1~F-4 + check_mcp_servers.py（m-2）| 1d / **1.5d** | 4 故障用例全过 + metadata 完整 |
| **3** | pilot weather server + 5 性能预算 | 1d / **1.5d** | 5 数字全达标 |
| **4** | PR-8 收尾（CI hook + lessons + observability）| 0.5d / **0.75d** | pre-commit + dashboard |
| **4 末** | §6.1 接受门槛 → ship PR-8 | — | tag `mcp-v4-pr8` |
| **5+** | PR-9 scale（先 §4.1 盘点 → Type B 拆 wrapper → 迁 Type A）| — | — |

**PR-8 总估时：6d**（v0.2 估 4d，+50% — 反映 Day 0 实际 1.5d 模式）

---

## 13. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| macOS RLIMIT_AS 不可靠 → 内存超 | 中 | 中 | §8 已测，超 2GB 砍 1 pilot 工具 |
| ~~F-3 `tc` sudo 阻塞~~（M-1 修订）| ~~中~~ | ~~中~~ | **已消除** — 改用 sleep 模拟 |
| AB router fallback 路径有 bug | 中 | 高 | §3.3 dual-track 保留老路径 + §3.5 pytest |
| v3 plan 范围漂移 | 中 | 中 | §1 Non-Goal 明确 |
| PR-9 Type B 拆 wrapper 工作量低估 | 高 | 高 | §4.1 盘点前置 |
| supervisor.py 文件已存在但未接 | 已知 | 中 | §3.4 dual-track |
| 17 未提交 MCP 文件与 PR-8 冲突 | 中 | 高 | §15.1 划分到 PR-7.5 |

---

## 14. 与 v0.1 提案的差异追溯

（同 v0.2 §14，16 项反馈全闭环）

---

## 15. 决策与同步

### 15.1 17 未提交 MCP 文件归属（C-2 决策）

```
未跟踪 (7) / 已修改 (10) MCP 相关文件
        │
        ├─ PR-7.5 单独 ship（Day 1 前 commit）
        │   ├─ mcp_ab.py
        │   ├─ ab_router.py
        │   ├─ mcp_tools.py
        │   ├─ mcp_alerts.py
        │   ├─ ab_metrics.py
        │   ├─ mcp/config.py（已重写）
        │   ├─ mcp/fake_host.py
        │   ├─ .github/workflows/mcp-ci.yml
        │   ├─ api/router.py（新增 mcp_ab 路由）
        │   └─ tools/{calc,greet,time,operation_log,resume_parser,skill_tool}.py
        │       （v4 工具升级 Pydantic InputModel）
        │
        └─ PR-8 范围
            ├─ host.py 改造（§3.4 4 处）
            └─ supervisor.py 接通（已存在，仅 host.py 改 import + spawn/shutdown 调用）
```

**Commit 消息策略**：
- PR-7.5: `chore(mcp): ship 17 uncommitted MCP files (v4 PR-1b/c residue)`
- PR-8: `feat(mcp): host.py 接 supervisor (dual-track §3.3)`

### 15.2 roadmap 同步（M-5 任务）

`docs/roadmap-2026-h2.md` 在 PR-8 ship 前更新：

| 阶段 | 原估时 | 修订 |
|---|---|---|
| P5-1 多租户 | 已 ship | — |
| P5-2 邀请 | 已 ship | — |
| P6-MCP PR-8 supervisor pilot | (v0.1 估 4d) | **6d**（v0.3 重估）|
| P6-MCP PR-9 scale 38 工具 | (v0.1 估 2-3d) | **9.5d**（已盘点）|
| P6-MCP 总计 | 6-7d | **15.5d** |

### 15.3 重做 supervisor 触发条件
- F-1~F-4 任一恢复 > 10s
- 内存稳态 > 4GB
- 数据丢失（rollback 1 个 op 失败）

### 15.4 v0.4 候选（推到下版）

- **m-1**: ADR D5 退避算法优先级提升（比 D7 资源监控更重要）— 估时在 PR-8 Day 1-2 跑出 F-1~F-4 数据后定
- m-2: 已合并到 v0.3 §12 Day 2
- m-3: 已合并到 v0.3 §5

---

## 16. 工具盘点事实源同步（C-1 修复）

**38 工具 / 4 Type A / 34 Type B / 0 Type C** —— 以 `docs/mcp-v4-pr9-tool-inventory.md §2` 大表为唯一事实源。

| 类型 | 数量 | 文件 |
|---|---|---|
| A 纯 tool | 4 | calc_tool / greet_tool / time_tool / docs_search_tool |
| B service wrapper | 34 | 其余所有 |
| C 流式 | 0 | — |

---

## 17. 下一步

1. ✅ 写 v0.3（this turn）
2. 修 inventory 数字（C-1，this turn）
3. Day 0.5：跑冷启动基线测（M-2）
4. PR-7.5 ship 17 未提交文件（C-2）
5. Day 1：改 host.py 4 处（§3.4）
6. Day 1 末：跑 §3.5 dual-track pytest
7. Day 2-3：pilot + 4 故障 + 5 性能预算
8. Day 4：PR-8 ship + 修 roadmap
