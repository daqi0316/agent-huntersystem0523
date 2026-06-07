# Momus 深度审核 — 后续 PR 规划 (chat 展示版) + 修正版

> **审核对象**: chat 中展示的"后续 PR 规划" (v0.7-v1.0 ship 后 8 项候选)
> **审核角色**: Momus (Plan Critic)
> **审核日期**: 2026-06-07
> **方法**: 对照 v0.5/v0.6+/v0.6c/v0.7-v1.0 经验, 6 维度找 gap
> **修正版**: 本文件 §6, 4-5 PR 重新设计 + 3 PR 删除/推迟

## 0. 跨候选系统性问题

### 0.1 [P0] 总估时 1.7-2.2d 系统性偏低, 实际 4-5d

chat 估时 (串行):
- v1.0b.1 (0.1d) + v1.0a.1 (0.1d) + v0.8.1 (0.5d) + v0.7.2 (0.5d) + v1.1 (1d) = 2.2d
- 不含 ship report (每个 PR 150+ 行文档) + commit message + tag 流程
- v0.5 节奏: 1 commit + 1 ship report = 单 PR ~0.2-0.3d **额外**时间

**真实估时**:
- v1.0b.1: 0.3d (含 ship report)
- v1.0a.1: 0.2d
- v0.8.1: 0.7d (含 Popen 调试 + 报告)
- v0.7.2: 0.7d
- v1.1: 1.5d (E2E 场景真实复杂度)
- **总 3.4d 串行 / 2.7d 并行** (而非 1.7-2.2d)

### 0.2 [P0] v0.9 "candidate_search 归位" 决策逻辑倒置

chat 写 "v0.9 条件触发, 看负载决定". **但** v0.9 决策**前**需要测负载, 负载测量在 v0.8.1 (用 Popen + psutil 测真实资源) — **顺序应该**:
```
v0.8.1 (测真实负载) → 写 ADR 决策 → v0.9 (实施拆分)
```

**当前规划把 v0.9 列候选但 v0.8.1 后才知是否需拆** — 决策逻辑错。

**修正**: v0.9 移除候选清单, 推 v0.8.1 + ADR 后再评估。

### 0.3 [P0] v0.9 "归位"语义不明 (v0.4e 14 server e2e 已显示 mcp-candidate tools=5)

chat 写 "candidate_search 归位". 实际 v0.4e 已 ship `mcp-candidate` server 5 工具, **包含** search 类工具.

**"归位"指什么**?
- 选项 A: search 工具在 mcp-candidate 已存在, "归位"无意义
- 选项 B: 拆独立 `mcp-candidate-search` server (单职责)
- 选项 C: search 工具名/分类归一 (e.g. `search_candidates` 重命名 `query_candidate_search`)

**chat 没明说** → plan 没法实施。**修正**: 查现状 + 写决策 ADR。

### 0.4 [P1] 跨 PR 依赖关系未明

chat 列 8 PR 候选, 但**没明说**依赖:
- v0.8.1 依赖 v0.8 已 ship (✓)
- v0.7.2 依赖 v0.7 + v0.7.1 已 ship (✓)
- v0.9 依赖 v0.8.1 负载数据 (chat 没说)
- v1.0b.1 依赖 v1.0b 已 ship (✓)
- v1.0a.1 依赖 v1.0a 已 ship (✓)
- v1.1 依赖 dev 栈稳定 (chat 提了, OK)
- v1.2 独立 (但 mutation test 风险大, 拆子项)
- v2.0 独立 (但需先看 mcp-interview 现状)

**修正**: 修正版加依赖图。

## 1. v1.0b.1 (SENTRY TRACES_SAMPLE_RATE typo 修) — 3 项问题

### 1.1 [P0] typo 修可能 break 已配 prod 环境

代码用 `os.getenv("SENTRY TRACES_SAMPLE_RATE")` (带空格). 修后改无空格, 但**已配 prod 的环境变量**可能仍带空格:
- 用户配 `SENTRY TRACES_SAMPLE_RATE=0.1` (带空格)
- 修后代码读 `os.getenv("SENTRY TRACES_SAMPLE_RATE")` (无空格)
- **返回 None** → Sentry 配置回退到默认

**修必须**:
- 兼容性 shim: 优先读无空格, fallback 读带空格 + 警告 deprecation
- 或 migration 文档: 用户手动重命名 env
- **不**在 PR 里加 deprecation warning (会污染日志), 只在 commit message + ship report 显式

**修正版**: typo 修 + 兼容 shim 暂留 1 版本周期。

### 1.2 [P1] v0.1d 估时不含 ship report

chat 估 0.1d. 实际含:
- 改 1 文件代码 (~5 行)
- 改 1 文件 .env.example (~1 行)
- 改 check_env_keys.py 删 SKIP_KEYS 2 行
- 重跑 check_env_keys.py --strict 验 0 缺
- ship report (~150 行)
- commit + tag
- **真实 0.3d**

**修正版**: 估时 0.3d.

### 1.3 [P1] 没写测试

typo 修后**没测试**验新 key 真的被读到. 风险: 修后某 import typo 导致无感失败.

**修正版**: 加 1 测试 `test_sentry_traces_sample_rate_reads_correctly` (断言 `os.getenv("SENTRY TRACES_SAMPLE_RATE")` 返 0.1 不是 None).

## 2. v1.0a.1 (ci.yml 改 pull_request 触发) — 3 项问题

### 2.1 [P1] 估时 0.1d 不含 ship report

真实 0.2d (1 行 yml 改 + ship report 100+ 行).

**修正版**: 估时 0.2d.

### 2.2 [P1] PR 早期发现可能产生 noise

每次 PR 跑 env check. 仓库**低频 PR** noise 极小, 但**外部贡献者 PR**:
- 无 secrets 权限
- fork PR 默认**无 GH Actions secrets** (除显式 opt-in)
- 我们的 env check **不**用 secrets (grep 代码, 不读 secrets), 应 OK
- 但**需**显式确认 `permissions: read-all` 或 `pull-requests: read` 权限足够

**修正版**: ci.yml 改 `permissions: read-all` + `on: pull_request: branches: [main]` + 文档化"对 fork PR 不需要 secrets".

### 2.3 [P2] v1.0a.1 价值低

chat 自承 "push 触发已能发现". **PR 早期发现** 价值在"代码 review 前阻止 PR 合入", 但本仓库 PR 频率低, push 触发 + reviewer 已有防护.

**修正版**: v1.0a.1 估时**可推迟**到下个 CI 改 batch (与 v1.2 合并), 不单独立 PR.

## 3. v0.8.1 (fd/memory 真实测量) — 5 项问题

### 3.1 [P0] 方案选 subprocess.Popen 还是 psutil 缺验

chat 决策点 4 写 "选 subprocess.Popen 还是 psutil? 推荐 B 验下". 实际**没验** — **必需 grep 验**:

```bash
grep -rn "import psutil\|from psutil" /Users/qixia/agent-huntersystem0523/apps/api/
```

**如 psutil 已有** → 用 psutil (跨平台, 1 行 `process.open_files()` 拿 fd).

**如 psutil 没** → 选 A (subprocess.Popen + lsof/ps 命令), **不引入新依赖** (CLAUDE.md 鼓励).

**修正版**: **先 grep 验**, 后定方案. 实施前必查.

### 3.2 [P0] subprocess.Popen + MCP 协议测试割裂

v0.8 脚本测 `lifecycle_one` (spawn + initialize + list_tools + shutdown, 全套 MCP协议). 改 Popen 后:
- Popen 起进程 → 拿到 PID → 等几秒 → kill
- **不**测 MCP 协议 (initialize + list_tools)

**取舍**:
- 方案 A: Popen + 独立 mcp 测 (拆 2 部分, 复杂度 ↑)
- 方案 B: Popen + 等几秒 + kill (只测资源, **不**测 MCP 协议)
- 方案 C: 双轨: stdio_client 测协议 + Popen 测资源

**推荐 B**: v0.8.1 目的是**fd/memory 测量**, MCP 协议测由 v0.4e 14 server e2e 14/14 覆盖. **不重复**.

**修正版**: v0.8.1 重写 `_lifecycle_one` 用 Popen 替代 stdio_client, 移除 MCP 协议测部分.

### 3.3 [P1] trial 间 sleep 0.5s 资源释放不够

v0.8 trial 间 `await asyncio.sleep(0.5)` 资源释放. 改 Popen 后, **Popen 进程退出但 fd 释放**延迟更长 (无 mcp 库 wrapping, OS 回收 ~1-2s).

**修正**: trial 间 sleep 0.5 → **1.5s**, 总时长 +30s (30 trial × 1s), 可接受.

### 3.4 [P1] PID 收集 420 个, ps 命令批量调用开销

v0.8 重测 30 实验 × 14 server = 420 PID. 每次 lsof / ps 启动 ~50ms × 420 = 21s 额外开销.

**修正**:
- 用 `lsof -p <pids>` 一次传多个 PID (逗号分隔) — 1 调用拿所有 fd
- 用 `ps -o rss= -p <pids>` 同理
- 总开销降到 30 × 2 命令 = 60 命令 × 50ms = 3s

**或**加 psutil 库 (`process.open_files()` / `process.memory_info().rss`) — 1 行拿 1 进程, 420 调用但每个快 (5ms).

### 3.5 [P2] 报告数字解读缺指南

v0.8.1 重测得真实数字后, **怎么解读**:
- 14 server 并行 RSS 800MB? 800MB/server? 总 800MB?
- fd 200/server? 上限多少?
- P95 wall 应**比** v0.8 baseline 大多少? 小多少?

**修正版**: 报告**含**:
- per-server RSS 数字 (P50/P95/max)
- per-server fd 数字
- 与 macOS 默认 (ulimit -n 256) / Docker 默认 (1024) 对比
- 如超限, **写 ADR 推 v0.8.2 修复**

## 4. v0.7.2 (skill_cli 鉴权 + 审计) — 5 项问题

### 4.1 [P0] 鉴权方式选项 A (JWT token) 实际不可行

chat 决策点 2 列 3 选项:
- A: CLI 时输 admin token → **CLI 操作者从哪拿 token**? 需 `auth_cli login` 流程 → **循环依赖** (新增 auth_cli 又要鉴权)
- B: auth_service 查 user.role → 需要 DB 连接 + 鉴权, 复杂度大
- C: pre-shared key (per-host 文件) → **最实用**, 但 chat 没说

**修正版**: 默认选 C (per-host `$HOME/.skill_admin_key` 文件), B 作未来 v0.7.3 选项.

**实施**:
```python
async def require_admin_key():
    key_path = Path.home() / ".skill_admin_key"
    if not key_path.exists():
        raise SystemExit("admin key not found: ~/.skill_admin_key")
    provided = os.environ.get("SKILL_CLI_ADMIN_KEY") or input("admin key: ")
    expected = key_path.read_text().strip()
    if not hmac.compare_digest(provided, expected):
        raise SystemExit("invalid admin key")
```

### 4.2 [P1] 审计 log 字段不足

chat 字段 `ts / action / skill / user / result`. **应加**:
- `before_enabled`: 改前状态 (True/False)
- `after_enabled`: 改后状态
- `reason`: 操作者备注 (可选)

**修正版**: 6 字段 `ts / action / skill_name / user / before / after`. 便于回溯.

### 4.3 [P1] v0.7 测试可能 break

v0.7.1 测试 (`test_cli_enable_disable_roundtrip`) 调 `enable_skill` 不带鉴权. v0.7.2 加 require_admin 鉴权后, **无 key 文件时** 鉴权 fail → CLI 抛 SystemExit → 测试 fail.

**修正版**:
- 测试用 `tmp_path + monkeypatch` 隔离 `$HOME/.skill_admin_key` (临时创建)
- 或 v0.7.2 加 `SKILL_CLI_REQUIRE_ADMIN=0` env 跳过鉴权 (dev/CI 模式)
- 推荐后者 (env 控 vs 文件创建)

### 4.4 [P1] 审计 log 持久化方式选 α vs β

chat 提 "α: .omo/skill_cli_audit.jsonl vs β: DB 表". **推荐 α** (jsonl, gitignore, 无 migration).

但**没提并发写风险**:
- 多 CLI 进程并发写同一 jsonl 文件 → **行交错, 解析乱**
- **修**: 用 `fcntl.flock` 文件锁 或 单进程写 + 进程内 queue 异步刷盘
- **简版**: 接受**单进程 CLI**假设 (CLI 本来就是单进程, 不像 server 并发), 不加锁.

### 4.5 [P2] 审计 log gitignore

v0.7.2 写 `.omo/skill_cli_audit.jsonl` — 需加 .gitignore. **v0.7 ship 时已加 `.omo/skill_state.json`**, 但 jsonl **未**加. 需 v0.7.2 补.

## 5. v1.1 (Phase D E2E) — 3 项问题

### 5.1 [P0] 估时 1d 偏低, 真实 E2E 场景复杂度

chat 估 1d "Playwright + 真实后端, 14 server 都跑". 实际 E2E 场景:
- 上传简历 → LLM 解析 → 候选人创建 (需要真实 PDF + LLM mock)
- 评估打分 → 推荐 → 面试预约 (跨多个 server)
- 每个场景 playwright test 30-60 分钟调试

**真实估时 2-3d** (4-5 playwright test 覆盖关键路径).

**修正版**: 估时 1.5d, 范围限制在 "已有 verify-login-e2e.ts 扩展 + 1-2 个核心业务流".

### 5.2 [P0] "14 server 都跑" 不明确

v0.4e 14 server e2e **已** 14/14 跑过 (顺序). v1.1 "全跑" 指什么?
- 选项 A: 重跑 v0.4e e2e (重复, 无价值)
- 选项 B: 端到端**业务流** 跨多 server (上传 → 解析 → 评估 → 推荐)
- 选项 C: 全 14 server 并行 spawn (v0.8 已做)

**推荐 B**: 跨 server 业务流, 真实价值.

### 5.3 [P1] 真实后端 LLM mock 问题

Playwright 跑真实后端, 但 v1.1 业务流调 LLM 解析简历. **真实 LLM 慢 + 不可预期**.

**修**:
- 跳过 LLM 部分 (CI 模式)
- 或 mock LLM 返固定候选人数据 (e2e 测业务流, 不测 LLM 质量)

**修正版**: v1.1 测业务流**不含** LLM, mock LLM 返固定响应.

## 6. 跨候选 (v1.0a.1 / v0.8.1 / v0.7.2 / v1.1) — 3 项问题

### 6.1 [P1] 测试隔离矩阵扩大

v0.7.2 加 require_admin 后, v0.7.1 测试 (无 key) 需隔离. 多个 v0.7.x 测试同时跑, 审计 log 写同一文件. 测试矩阵扩大.

**修正版**:
- 审计 log 测试用 `tmp_path + monkeypatch`
- v0.7.1 测试加 `SKILL_CLI_REQUIRE_ADMIN=0` env 跳过鉴权

### 6.2 [P1] 回滚矩阵复杂化

v0.7.2 + v0.8.1 + v1.0a.1 + v1.0b.1 4 PR 串行, 各自回滚独立. 但**测试已 ship** 与**代码已 ship** 不一定一致:
- v0.7.2 revert 后, v0.7.1 测试仍能跑 (require_admin 可 bypass)
- v0.8.1 revert 后, v0.8 测试仍能跑 (有数字报告, 不是 fail)

**OK 兼容性** — 但需每个 ship report 显式写 "回滚影响范围".

### 6.3 [P2] v1.2 mutation test 风险低估

chat 估 v1.2 (Phase E CI/CD 强化) 2d, 含 mutation test. mutation test 工具 (mutmut / cosmic-ray):
- CI 时间 +50-100% (慢测)
- 项目**没 mutation baseline** (第一跑全失败, 需配置 survive mutants)
- 价值: 找测试盲点 (未覆盖的代码路径)

**修**:
- v1.2 mutation 拆 v1.2c (单独 PR), 不与覆盖率阈值合并
- 第一跑预期失败多, **人工 triage** survivors
- 估时修正: 1d 跑 + 1d triage = **2d** (不是 chat 估的 0.5d 合并)

## 7. v2.0 (mcp-interview/mcp-evaluation Bheavy) — 2 项问题

### 7.1 [P0] mcp-interview 现状未查, 估时盲点

chat 估 4d. **没查** mcp-interview 现状:
- 调 LLM 吗? 多长任务?
- 现有 handler 实现?
- mcp-evaluation 类似

**修**: **先查** `app/agents/interview_agent.py` / `app/agents/evaluation_agent.py` / `app/mcp_servers/builtin/interview_server.py` 等. 估时**等查完后定**.

### 7.2 [P1] 估时偏高 (v0.6 基础设施已建)

chat 估 4d. v0.6 改造 mcp-resume 5 文件 (parse_task / parse_worker / raw_resume API / 工具 / metadata), **新加 mcp-interview 时**:
- parse_task 框架**已建** → 复用, 1 文件改 (改 imports)
- raw_resume API **已建** → 加新 endpoint 或复用 generic
- 工具 + metadata **已建** → 加 2 工具

**真实估时 2-3d** (不是 4d).

## 8. Momus 修正版规划

按上述 24 项 gap, 修正版**4-5 PR 重新设计 + 3 PR 删除/推迟**:

### 8.1 修正版 PR 清单 (4 PR, 总 2.7d 串行 / 2.0d 并行)

| 阶段 | 范围 | 估时 | 并行 | 依赖 |
|---|---|---|---|---|
| **v1.0b.1** | 修 SENTRY TRACES_SAMPLE_RATE typo + 兼容 shim (暂留带空格 1 版本周期) + 1 测试 + ship report | 0.3d | agent 1 | v1.0b ✓ |
| **v0.7.2** | skill_cli 鉴权 (per-host pre-shared key 选项 C) + 审计 log 6 字段 (ts/action/skill_name/user/before/after) + jsonl gitignore + v0.7.1 测试兼容 (env 跳过) | 0.7d | agent 1 | v0.7 + v0.7.1 ✓ |
| **v0.8.1** | subprocess.Popen 替代 stdio_client (只测资源, 不测 MCP 协议) + psutil 库加 (如项目未用) 或 lsof 批量 (如已用) + trial sleep 0.5→1.5s + 30 实验重测 + 真实 fd/memory 报告 | 0.7d | agent 2 | v0.8 ✓ |
| **v1.1** | Phase D E2E: 跨 server 业务流 (上传→解析→评估→推荐) + 1-2 个 playwright test + mock LLM | 1.5d | agent 2 | 14 server e2e ✓ |

### 8.2 删除/推迟的 PR

| 阶段 | 决策 | 理由 |
|---|---|---|
| v1.0a.1 (ci.yml pull_request 触发) | **推迟到 v1.2 合并** | 价值低, push 触发已能发现, 不单独立 PR |
| v0.9 (candidate_search 归位) | **从候选清单删除** | "归位"语义不明 (已在 mcp-candidate), 真实决策需 v0.8.1 负载数据 → ADR → 实施, 不在 backlog |
| v1.2 (Phase E CI/CD 强化) | **拆分 v1.2a/b/c 3 子 PR** | mutation test 风险大, 不与覆盖率合并; 总估时 2d → 拆 3 PR 各 0.5-1d |
| v2.0 (mcp-interview/evaluation Bheavy) | **先查现状再估时** | 估时盲点, chat 估 4d 实际可能 2-3d |

### 8.3 跨阶段依赖图

```
v1.0b.1 ──┐
          ├──> (无依赖, 可并行) ──> ship
v0.7.2 ──┤
          │
v0.8.1 ──┤
          ├──> (无依赖, 可并行) ──> v1.1 (依赖 v0.8.1 数字, 间接)
v1.1  ───┘
```

**总 2.7d 串行 / 2.0d 并行 (2 agent 跑 4 PR, v0.7.2 + v0.8.1 并行)**.

## 9. 待 sign-off 决策

1. **走模式 A (串行 2.7d) / B (并行 2.0d) / C (选最有价值单 PR 0.5d)**?
2. **v0.7.2 鉴权方式选 C (per-host pre-shared key)** (其他选项有循环依赖/复杂度)?
3. **v0.8.1 加 psutil 依赖** (如项目未用) / **不引入新依赖** (subprocess + lsof)?
4. **v1.0a.1 推迟到 v1.2 合并** (不入短期 backlog)?
5. **v0.9 从候选清单删除** (等 v0.8.1 负载数据后再决策)?
6. **v2.0 先查 mcp-interview/evaluation 现状再估时** (chat 估 4d 估时盲点)?

## 10. 引用

- chat 后续 PR 规划: 用户"先做一个规划"提示
- v0.7-v1.0 修正版: `.omo/plans/v0.7-v1.0-momus-review.md` (并行 2d 模式)
- v0.6+ 修正版: `.omo/plans/v0.6-plus-replan.md` (v0.6 异步化模式参考)
- v0.5 Momus 修 6 项: `.omo/plans/v0.5-replan.md` §8
- v0.6c Momus 修 6 项: `.omo/plans/v0.6c-momus-review.md`
- 累计 ship reports: `docs/mcp-v4-v0.{5a,5b,6a,6b,6c,6c.1,7,7.1,8,1.0a,1.0b}-ship-report.md`
- check_env_keys.py: `scripts/check_env_keys.py` (v1.0a ship)
- skill_cli: `apps/api/app/scripts/skill_cli.py` (v0.7.1 ship)
- v0.8.1 决策点依赖: `.omo/plans/v0.7-v1.0-momus-review.md` §7.4 (lsof fail-open 模式)
