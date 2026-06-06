# MCP v4 PR-8 Supervisor Pilot — v0.2 (Momus 修订版)

> **修订自**: v0.1 提案 + Momus 审核 6.0/10
> **目标评分**: ≥ 8.0/10
> **上游**:
> - `.omo/plans/mcp-dual-track-refactor.md` (v3 plan 范围更广)
> - `docs/mcp-v4-impl-report.md` (PR-0~7 已 ship)
> - `apps/api/app/mcp/{host,supervisor,registry,config,ab_router}.py` (现状)
> **最后更新**: 2026-06-06

## 0. 变更摘要（vs v0.1）

| 项 | v0.1 | v0.2 (本版) | 触发 |
|---|---|---|---|
| Pilot 工具数 | 5 | **2**（calc + weather）| C-1 pilot 是 pilot，不是 wave 1 |
| 故障注入 | 1 (kill -9) | **4**（F-1~F-4：硬杀/优雅/卡死/伪死）| C-2 1 种不构成验证 |
| Host 改造 | 1d 全切 | **dual-track**（保留 AsyncExitStack 作 fallback）| C-3 隐式大重构 |
| ADR 问题 | 7 同权 | **P0/P1/P2** 分级 | M-1 前提 vs 优化要分开 |
| 工具盘点 | "机械迁 19-21" | **Type A/B/C 分类前置** | M-2 多数不是纯 tool |
| 回滚条件 | 模糊 | **3 档门槛 + git tag** | M-3 + m-4 |
| AB router | 没说 | **策略 A**（subprocess 失败 → in-process fallback）| M-4 |
| 性能预算 | "性能基准" | **5 数字 + 测量方法** | M-5 |
| 命名 | PR-2 / PR-2.5 | **PR-8 / PR-9**（接续 v4 PR-0~7）| m-1 |
| 引用 v4 教训 | 缺 | **§11 显式对照表** | X-3 |

---

## 1. Goal / Non-Goal

### Goal
1. **验证 supervisor 设计** 在 AsyncExitStack 限制下能真重启 server（4 种故障全过）
2. **建立 server 拆分模板** —— 2 工具迁通后，PR-19 机械复用
3. **5 性能预算达标** —— 冷启动 / 热调用 / 重启 / 内存 / fallback 5 指标

### Non-Goal（明确不做）
- ❌ 全 22 工具一次性迁（推到 PR-9 scale）
- ❌ 重写 AsyncExitStack 路径（保留作 PR-8 fallback）
- ❌ 新增远程 MCP server 能力（C 轨道）
- ❌ 改 AB router 算法
- ❌ Type C 流式 / SSE 工具（PR-10+ 单独设计）

---

## 2. 7 个 ADR 问题（P0/P1/P2 分级）

> ADR 文件: `docs/adr/0007-mcp-supervisor.md`（v0.2 启动 0.5d 起草）

### P0（PR-8 启动前必须答）

| # | 问题 | 决定 | 理由 |
|---|---|---|---|
| **Q1** | 重启策略：close-then-respawn vs 整 stack 重建 | **A: close-then-respawn（同 stack）** | 渐进式，原路径保留 |
| **Q4** | session 所有权：host 持 session，supervisor 持 process——重启时序 | **A: supervisor 先拆** | supervisor 是 process 生命周期 source of truth；session 跟着 process 走 |
| **Q6** | 冷启动分批：13 server 全开 vs 3 批 | **A: 3 批（core/secondary/lazy）** | PR-8 2 pilot 工具都在 core 批（< 2s 启动目标）|

### P1（PR-8 跑出数据后定，可迭代）

| # | 问题 | 备选 | 状态 |
|---|---|---|---|
| **Q2** | 故障检测：psutil 轮询 vs call 失败懒检测 | **A: 双轨**（psutil 3s 轮询 + call 失败兜底）| 实战"慢死"只能主动检测 |
| **Q3** | 退避：指数 vs 固定 + circuit breaker | TBD | PR-8 数据后定 |
| **Q5** | 优雅关停：SIGTERM→wait→SIGKILL | **A: 5s wait** | 长跑 skill 需要 in-flight 完成 |

### P2（PR-9 scale 阶段答）

| # | 问题 | 状态 |
|---|---|---|
| **Q7** | 资源上限：单进程 cap | TBD（macOS RLIMIT_AS 不可靠，§8 验证后定）|

---

## 3. PR-8 Pilot 范围

### 3.1 工具选择（2 个，覆盖 2 条轨道）

| 工具 | 轨道 | 选它的理由 | 不选什么 |
|---|---|---|---|
| **calc** | A (内置) | 纯函数 / 验证基础通路 / 已 register（v4 工具升级）| — |
| **weather** (skill) | B (skill) | 外部依赖 / 网络故障注入天然场景 / 已存在 skill server | — |

**延后到 PR-9**（pilot 验证后）：
- **candidate**（DB + 多租户 RLS）→ 验证跨进程 DB session
- **resume_parser**（file ref，>1MB）→ 验证大 result pipe 不爆
- **install_skill**（admin + 元操作）→ 验证 capability=RBAC + 重启后状态恢复
- **jd**（配 resume_parser）→ 业务配对
- **operation_log**（写操作）→ 验证 capability=write 路径

**推到 PR-10+**（不在 pilot/scale 范围）：
- **dashboard / interview / application / evaluation**（service wrapper 类型，Type B）

### 3.2 4 种故障注入

| # | 场景 | 工具 | 验收 | 恢复 SLA |
|---|---|---|---|---|
| **F-1** | `kill -9` 硬杀 | `kill -9 <pid>` | 新 session 自动接 call | < 3s |
| **F-2** | `kill -15` 优雅 | `kill -15 <pid>` | in-flight call 完成，新 session 接 | < 5s |
| **F-3** | 网络卡死 | `tc qdisc add delay 30s` on loopback | call 超时降级，进程不死 | call timeout 5s |
| **F-4** | 伪死（stdio pipe 在但 handler hang）| 子进程 `time.sleep(60)` | supervisor 主动 kill + 重启 | < 10s |

每个故障：
- 1 个 pytest 用例（`tests/mcp/test_supervisor_fault_injection.py`）
- 1 个 Prometheus 指标埋点
- 1 段 ADR 记录观测数据

### 3.3 AB router fallback 策略（dual-track）

**决定 A**：supervisor 失败 → fallback 到 in-process handler（PR-1c 旧路径）

```python
# apps/api/app/mcp/host.py: call_tool 流程
async def call_tool(self, name, args):
    try:
        # 新路径：subprocess + stdio
        return await self._subprocess_call(name, args)
    except (SubprocessDown, CallTimeout) as e:
        # Fallback：in-process handler（PR-1c 路径）
        logger.warning("subprocess fallback to in-process: %s", e)
        return await self._inprocess_call(name, args)
```

**验收**：supervisor 整体关闭时，2 工具仍可调（降级模式跑通）

---

## 4. PR-9 Scale 范围（前置盘点）

### 4.1 工具"Type A/B/C"分类（PR-8 启动 0.5d 同步做）

| 类型 | 定义 | 迁移方式 | 范围 |
|---|---|---|---|
| **A — 纯 tool** | 短函数 / 独立调用 / 无状态 | 直接迁 server（机械）| 大部分内置工具 |
| **B — service wrapper** | 带 session / 状态 / 长事务 | 拆 thin tool wrapper → service 内部调 | dashboard / interview / application / evaluation |
| **C — 流式 / SSE** | handler 持续输出 | 单独设计（不在 PR-9 范围）| TBD |

**输出**：`docs/mcp-v4-pr9-tool-inventory.md`（每工具一行：name / 轨道 / 类型 / 迁移方式）

### 4.2 PR-9 范围定义
- 迁 Type A 全部
- 拆 Type B → thin tool wrapper 后迁
- Type C 推到 PR-10+（不阻塞）

---

## 5. 性能预算

| 指标 | 目标 | 测量方法 |
|---|---|---|
| 冷启动 P95 | **< 2s**（PR-8，2 工具）| `time make api:dev` + `mcp_server_startup_seconds` |
| 热调用 P95 | **< 50ms** | `/metrics mcp_call_duration_seconds` |
| 重启 P95 | **< 3s**（F-1）/ < 5s（F-2）| F-1 ~ F-4 注入 + 测 kill→next_call |
| 内存稳态 | **< 2GB**（5 subprocess）| `docker stats` + `psutil.virtual_memory()` |
| AB router fallback P95 | **< 100ms**（含 in-process）| F-1 时同步测 fallback 路径 |

---

## 6. 回滚条件 + 退出标准

### 6.1 三档门槛

| 档位 | 触发条件 | 动作 |
|---|---|---|
| **接受** | F-1~F-4 全过 + 5 性能预算全达标 | ship PR-8，进 PR-9 |
| **重做 supervisor** | 任一 F 重启 > 10s **或** 内存 > 4GB **或** 数据丢失 | 回滚 PR-7 + 改 supervisor 设计（重走 ADR）|
| **放弃 v4 路线** | AsyncExitStack 限制无解 **或** stdio 性能 < 20 P95 | 锁定 v3 方案（in-process）+ 关 PR-9 范围 |

### 6.2 回滚方法

- 用 **git tag** 而非 migration 表：每 PR ship 前 `git tag mcp-v4-pr8-pre`
- 失败 → `git checkout mcp-v4-pr8-pre` + 删新 server 目录
- DB schema 不动（PR-8 不改 model），回滚 = 代码回滚

---

## 7. 用户体验影响 + 灰度策略

### 7.1 用户感知差异

| 路径 | 延迟 |
|---|---|
| 旧（in-process）| < 1ms |
| 新（subprocess + stdio）| ~5-10ms |

**用户感知**：单次 tool call 慢 5-10ms — 端到端 chat（含 LLM 1-3s）看不明显。

### 7.2 灰度策略（沿用 AB router PR-1b 模式）

| 阶段 | 配置 | 流量 |
|---|---|---|
| PR-8 ship 前 | `MCP_AB_PERCENT=0` | supervisor 拉起但不接流量，in-process 全跑 |
| PR-8 ship 后 24h | `MCP_AB_PERCENT=10` | sticky hash 10% 流量走 subprocess |
| 观察稳定 | `MCP_AB_PERCENT=50` | 50% |
| 全量 | `MCP_AB_PERCENT=100` | 全 subprocess |

每个 percent 跑 24h 看 Prometheus + Sentry 错误率，无异常再升档。

---

## 8. macOS 资源限制验证（PR-8 Day 0 必做）

**已知问题**（`apps/api/app/mcp/supervisor.py` 注释）：`RLIMIT_AS` 在 macOS 行为不同，容错。

**PR-8 Day 0 任务**：
1. dev 机跑 5 subprocess（2 pilot 工具 + 3 个 dummy 进程）
2. 测稳态内存 + 进程数 + FD 数
3. 输出 `docs/mcp-v4-pr8-macos-resource-test.md`
4. **决策点**：
   - < 2GB 稳态 → §5 预算成立，进 PR-8
   - 2-4GB → 砍 1 pilot 工具（weather 延后）
   - > 4GB → §6.1 重做门槛触发，supervisor 加 cgroup（macOS 不支持 → 推 Linux staging）

---

## 9. Observability 门槛

| 指标 | 已存在 | PR-8 补 |
|---|---|---|
| `mcp_calls_total` | ✅ | — |
| `mcp_call_duration_seconds` | ✅ | — |
| `mcp_server_up` | ✅ | **加 alert**: < 1 持续 1min → Sentry |
| `mcp_server_restarts_total` | ✅ | **加 alert**: > 3/小时 → Sentry |
| `mcp_supervisor_lag_seconds` | ❌ | **新增**（kill→reconnect 时长，PR-8 决定 histogram bucket） |
| `mcp_ab_fallback_total` | ❌ | **新增**（subprocess 失败 → in-process 兜底次数）|

---

## 10. CI 守门

- `scripts/check_mcp_servers.py` 已存在：tools / skills / config 三类
- **PR-8 补**：加 `supervisor_lifecycle` 检查
  - 启动 → F-1（kill -9）→ 自动恢复 → 工具调用 OK
  - pre-commit hook：`bash -c "cd apps/api && .venv/bin/python -m pytest tests/mcp/test_supervisor_lifecycle.py -v"`

---

## 11. 引用 v4 教训（兑现对照表）

| v4 教训（impl report §2）| 本方案如何兑现 |
|---|---|
| AsyncExitStack 跨 task cancel 错 | §3.3 保留 in-process fallback，不破坏现有 |
| AB router 总是 wrap（PR-1b）| §7.2 灰度策略延续 AB router，不绕过 |
| register_tool 双用法 bug | PR-8 不动 tool 注册逻辑（只动 server 拆分）|
| CI 脚本用 venv python | §10 显式 `.venv/bin/python` |
| dead import 破坏 build | PR-8 import 检查：supervisor 引入的 import 全在 requirements.txt |
| 工具函数当装饰器用 → TOOL_METADATA 空 | PR-8 工具拆分前先跑 `scripts/check_mcp_servers.py` 验 metadata 完整 |

---

## 12. 时间线

| Day | 任务 | 估时 | 验证 |
|---|---|---|---|
| **0** | macOS 资源测（§8）+ ADR 起草（§2 P0 三问）+ 工具盘点（§4.1）| 0.5d | resource test 报告 + ADR PR |
| **1** | 改 host.py 接 supervisor（dual-track §3.3）| 1d | host.py 单元测试 |
| **2** | pilot calc server + 4 故障注入 F-1~F-4 | 1d | 4 故障用例全过 |
| **3** | pilot weather server + 5 性能预算（§5）| 1d | 5 数字全达标 |
| **4** | PR-8 收尾（CI hook §10 + lessons §11 + observability §9）| 0.5d | pre-commit + dashboard |
| **4 末** | **§6.1 接受门槛** 全过 → ship PR-8 | — | tag `mcp-v4-pr8` |
| **5+** | PR-9 scale 启动（先做 §4.1 盘点 → 拆 Type B wrapper → 迁 Type A）| — | — |

**PR-8 总估时：4d**（vs v0.1 提案 4d，schedule 不变但内部 task 颗粒度更细）

---

## 13. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| macOS RLIMIT_AS 不可靠 → 内存超 | 中 | 中 | §8 Day 0 测，超 2GB 立即砍 1 pilot 工具 |
| F-3 网络卡死检测不可靠 | 高 | 中 | §2 Q2 双轨：懒检测兜底 |
| AB router fallback 路径有 bug | 中 | 高 | §3.3 dual-track 保留老路径本身就是 fallback 测试 |
| v3 plan 范围漂移（scope creep）| 中 | 中 | §1 Non-Goal 明确边界 |
| PR-9 Type B 拆 wrapper 工作量低估 | 高 | 高 | §4.1 盘点前置，Type C 推 PR-10+ |
| supervisor.py 文件已存在但未接（host 路径）| 已知 | 中 | §3.3 dual-track：supervisor 接管新路径，AsyncExitStack 留作 fallback |

---

## 14. 与 v0.1 提案的差异追溯

| Momus 反馈 | 编号 | 解决位置 |
|---|---|---|
| 5 工具不是 pilot | C-1 | §3.1 缩到 2 |
| kill -9 不构成验证 | C-2 | §3.2 4 故障场景 |
| 改 host.py 是隐式大重构 | C-3 | §3.3 dual-track |
| 7 ADR 问题分 P0/P1/P2 | M-1 | §2 分级表 |
| 19 工具不是机械迁 | M-2 | §4.1 Type A/B/C 盘点 |
| 缺回滚条件 | M-3 | §6.1 三档门槛 |
| AB router 与 supervisor 关系 | M-4 | §3.3 策略 A |
| 性能基准无指标 | M-5 | §5 5 数字 |
| PR 编号混乱 | m-1 | §0 改名 PR-8/PR-9 |
| 5 工具缺 jd | m-2 | §3.1 jd 推 PR-9 |
| CI hook 没说 | m-3 | §10 pre-commit |
| 回滚用 git vs migration | m-4 | §6.2 git tag |
| observability 没说 | m-5 | §9 6 指标 |
| 用户体验影响 | X-1 | §7 |
| macOS RLIMIT 不可靠 | X-2 | §8 Day 0 测 |
| 失败案例未引用 | X-3 | §11 兑现对照 |

---

## 15. 下一步

1. 复审 v0.2 → 提交 Momus 二次审（目标 ≥ 8.0）
2. 通过后 → §2 P0 三问 ADR 起 `docs/adr/0007-mcp-supervisor.md`
3. §8 macOS 资源测结果确认 → 正式开 PR-8
4. 复审 v0.2 → §12 Day 0 启动

**未启动实现前**的所有修正项已落地到本文件。CI 守门与 Momus 二次审可作为启动开关。
