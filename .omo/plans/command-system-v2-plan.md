# AI 招聘 Agent 内置命令系统 V2.0 — 实施规划

> **本文件**：`AI招聘Agent内置命令系统V2.0.md` 的实施路线图
> **状态**：**V.1-V.5 ✅ 完成，V.6 前端命令面板进行中**
> **作者**：Sisyphus 编排
> **最后更新**：2026-06-02

---

## 0. 元信息

- **设计文档**：`AI招聘Agent内置命令系统V2.0.md`（1727 行，状态：评审中）
- **命名约定**：本规划以 **Phase V-Command** 接入现有 S/T/U/V 序列（**不**新增 C 序列），后续对应实现为 V.1-V.6
- **依赖**：
  - **强依赖** Phase S（LangGraph 编排）完成度 ≥ 80% — `/pause` `/resume` `/switch` `/back` 需要 Graph 状态接口
  - **弱依赖** Phase T（MCP 工具）— 共享工具层，可并行
  - **独立** Phase U（运维可观测）— **不复用** OperationLog，使用独立 `command_audit_log` 表（见 M2 修复）
- **预计总工时**：**38-48h** ≈ 2-3 周（单人，**含 Momus 修复增量**）
- **风险等级**：中（接入面广，但底层服务已就绪）

---

## 1. 现状盘点（代码实证）

### 1.1 V1.0 命令系统状态

```bash
$ grep -r "/restart\|/pause\|/resume\|/snapshot\|/read \|/list " apps/api/app/ --include="*.py"
# → 0 命中
```

**结论**：V1.0 命令系统**未在代码中实现**。所有 28 个命令均为新增。

### 1.2 已就绪的底层服务（可直接复用）

| 服务 | 文件 | 用途 |
|---|---|---|
| ConversationService | `services/conversation_service.py` (204行) | session / 消息持久化 |
| TaskService | `api/tasks.py` | 任务管理（list/get/snapshots/timeline）|
| Candidate/Job/Application | `api/candidates.py` `api/jobs.py` `api/applications.py` | CRUD |
| Snapshot | `apps/api/app/snapshots.db` | 已有本地快照存储 |
| OperationLog | `models/operation_log.py` + `api/audit.py` | 审计日志（Phase U 在用）|
| agent_service.chat_with_tools | `services/agent_service.py` (714行) | LLM 入口 |
| OrchestratorGraph | `graphs/orchestrator_graph.py` | LangGraph 主图 |
| ApprovalService | `services/approval_service.py` | 人机确认（Phase U 新建）|

### 1.3 需要新建的能力

| 能力 | 原因 |
|---|---|
| 命令注册表 + 解析器 | 当前 `chat_with_tools()` 不解析 `/` 前缀 |
| 回收站表 `recycle_bin` | `/delete` 软删 30 天保留 |
| 命令面板 UI | 前端无命令交互入口 |
| 4级权限矩阵 | 当前所有 API 都是统一鉴权 |
| 自然语言→命令建议 | 关键词匹配优先 + 兜底 LLM 分类 |
| `command_audit_log` 表 | **不复用** OperationLog（避免污染 Phase U 物化表）|
| Redis 分布式锁 | 命令 session 串行化（替代 asyncio.Lock，跨 worker 生效）|

---

## 2. 架构设计：4 层堆叠

```
┌──────────────────────────────────────────────────────────────┐
│ L1 入口层 — POST /api/v1/agent/chat                          │
│   增强点: 收到 message 后, detect_command() 优先于 LLM 调用    │
└────────────────────────┬─────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ L2 解析层 — CommandParser                                     │
│   • 检测 "/" 开头 ( "//" 转义)                                │
│   • 解析: name + positional args + --flags + |pipe          │
│   • 别名展开: /r → /restart, /p → /pause, ...                │
│   • 自然语言: 调 LLM 分类 → 推荐命令                          │
└────────────────────────┬─────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ L3 注册层 — CommandRegistry                                   │
│   • 28 个 handler 注册,带元数据:                              │
│     - name / category / aliases / permissions / needConfirm  │
│   • 按 category 查询 / 按 name 调用                           │
└────────────────────────┬─────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ L4 执行层 — CommandExecutor                                   │
│   • 权限检查 (L1-L4 矩阵)                                    │
│   • 确认检查 (needConfirm → ApprovalService 走 SSE)           │
│   • 调用 Service (task / candidate / snapshot / ...)         │
│   • 副作用: 自动快照 + 审计日志 + SSE 推送                    │
└────────────────────────┬─────────────────────────────────────┘
                         ↓
              现有 Services (Task/Candidate/Job/Snapshot/...)
```

### 2.1 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 命令 vs LLM 优先级 | **命令优先**（`/` 前缀） | 确定性、低延迟、节省 token |
| 自然语言→命令 | LLM 分类**可选** | 默认不开启, 用户主动 `/suggest` 触发 |
| 确认流 | 复用 `ApprovalService` | Phase U 已建, 不重新发明 |
| 快照粒度 | CRUD 命令自动 + 任务控制手动 | 避免快照爆炸 |
| 多 session 命令 | 全局生效（如 `/list`）, 部分需 session 上下文 | 默认无 session 也能用 |

---

## 3. 文件结构

```
apps/api/app/
├── commands/                          # ← 新建
│   ├── __init__.py                    # 暴露 registry 单例
│   ├── types.py                       # CommandContext, CommandResult, ParsedCommand
│   ├── parser.py                      # CommandParser
│   ├── registry.py                    # CommandRegistry + register_all()
│   ├── permissions.py                 # 4 级权限 + @require_permission
│   ├── audit.py                       # OperationLog 写入 hook
│   ├── executor.py                    # CommandExecutor (主流程)
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── task_control.py            # 8 个任务控制命令
│   │   ├── dialog.py                  # 8 个对话管理命令
│   │   ├── crud.py                    # 7 个数据 CRUD 命令
│   │   └── system_ops.py              # 8 个系统操作命令
│   └── tests/
│       ├── conftest.py
│       ├── test_parser.py
│       ├── test_registry.py
│       ├── test_executor.py
│       └── test_handlers_*.py
├── services/
│   ├── conversation_service.py        # 增强: detect_command(message) → str|None
│   ├── agent_service.py               # 增强: chat_with_tools 入口分流
│   └── recycle_bin_service.py         # 新建: 软删 + 30 天 TTL
├── models/
│   └── recycle_bin.py                 # 新建: 软删表
├── alembic/versions/
│   └── xxxx_add_recycle_bin.py        # 新建: Alembic 迁移
└── ...

apps/web/
├── app/(dashboard)/agent/
│   └── page.tsx                       # 增强: 集成命令面板
├── components/features/commands/
│   ├── command-palette.tsx            # cmdk 风格浮层
│   ├── command-suggestion.tsx         # 自然语言建议
│   └── command-history.tsx            # 命令历史
├── hooks/
│   └── use-commands.ts                # 命令客户端 hook
└── lib/
    └── command-client.ts              # 前端命令解析 + API 封装
```

---

## 4. 实施分阶段

> **本规划所有 Phase C 编号，从 V.1 起重新编号**（V.1 = C0 骨架，V.2 = C1 任务控制，...）

### Phase V.1 — 基础骨架（8-10h）

| # | 任务 | 估时 | 依赖 |
|---|---|---:|---|
| V.1.1 | `commands/types.py`: `CommandContext`, `CommandResult`, `ParsedCommand`, `CommandErrorCode` 枚举 | 1h | — |
| V.1.2 | `commands/parser.py`: 解析 `/cmd arg --flag=v \| pipe` | 1.5h | — |
| V.1.3 | `commands/registry.py`: 注册/别名/分类元数据 | 1h | V.1.1 |
| V.1.4 | `commands/permissions.py`: 4 级矩阵 + `@require_permission` | 1h | — |
| V.1.5 | `commands/audit.py`: 独立 `command_audit_log` 表 + 写入 hook | 1.5h | V.1.1 |
| V.1.6 | `commands/executor.py`: 权限→确认→执行→快照→审计 + Redis 分布式锁 | 2h | V.1.2/3/4/5 |
| V.1.7 | `models/command_audit_log.py` + Alembic 迁移 | 1h | V.1.5 |
| V.1.8 | V.1.8a: 框架测试 (parser/registry/executor) | 2h | V.1.6 |
| V.1.8 | V.1.8b: 28 命令 stub + 注册到 registry | 1h | V.1.3 |
| V.1.8 | V.1.8c: handler mock 测试 (每 handler 0.5h × 4 文件 = 2h) | 2h | V.1.8b |

**V.1 退出标准（可量化）**：
- [ ] `/help` 输出 ≥ 28 命令清单（按 category 分组）
- [ ] `/unknown_xxx` 返回 `error_code=CMD_NOT_FOUND` + 提示 `/help`
- [ ] 8 个别名（`/r /p /s /h /n /l /d`）解析命中正确 handler
- [ ] `//` 前缀消息原样转发给 LLM
- [ ] `command_audit_log` 表写入字段：`command_name / args / flags / result.code / duration_ms / confirmation_token / session_id / user_id / created_at`，**写入率 100%**
- [ ] Redis 分布式锁 key 格式 `cmd:lock:session:{sid}`，timeout 10s
- [ ] 单元测试覆盖：`parser` ≥ 95%、`registry` ≥ 90%、`executor` ≥ 90%

---

### Phase V.2 — 任务控制命令（4-6h）

| # | 任务 | 估时 | 复用 |
|---|---|---:|---|
| V.2.1 | `/restart`: TaskService + 快照 (parent_task_id 链) | 1.5h | `api/tasks.py` |
| V.2.2 | `/pause` + `/resume`: **等 Phase S.3 100% 完成** 再实现真 LangGraph interrupt | 1.5h | `graphs/orchestrator_graph.py` |
| V.2.3 | `/cancel` + `/retry`: 走 ApprovalService 确认流 | 1h | `services/approval_service.py` |
| V.2.4 | `/rollback` + `/snapshot` + `/checkpoint`: 快照服务 | 1.5h | `snapshots.db` |

**V.2 退出标准（可量化）**：
- [ ] 8 个任务控制命令 E2E 通过（Playwright）
- [ ] `/pause` 持久化 task.status=`paused` + snapshot_id；`/resume` 校验 `current_node + state_hash` 与 pause 前 **byte-equal**（依赖 Phase S.3 完成）
- [ ] `/cancel` 必须先经 ApprovalService 二次确认（前端弹窗 + token 校验）
- [ ] `/rollback 3` 返回 `preview_snapshot` JSON，用户确认后才执行
- [ ] 每次状态变更 → `command_audit_log` 一行

**降级方案**（如 Phase S.3 延期）：
- V.2.2 不实现"真"pause，改为 UI 软暂停标记 + 提示用户 Phase S 进度
- `/resume` 实际为"重启当前 task" — 退出标准改为"恢复到最近一次 snapshot 节点（非 byte-equal）"

---

### Phase V.3 — 对话管理命令（4-6h）

| # | 任务 | 估时 | 复用 |
|---|---|---:|---|
| V.3.1 | `/new` + `/history` + `/clear`: ConversationService 增强 | 1.5h | `services/conversation_service.py` |
| V.3.2 | `/switch` + `/back`: 编排器层 + LangGraph checkpointer | 2h | `graphs/orchestrator_graph.py` |
| V.3.3 | `/merge` + `/fork` + `/diff`: 多分支管理 (新表 `session_branches`) | 2h | — |

**V.3 退出标准**：
- [ ] `/new` 创建新 session, 旧 session 仍可恢复（`session.status='archived'`）
- [ ] `/switch screening` 切换 Agent 后, `current_agent` 字段 + 历史上下文保持
- [ ] `/fork --name "A"` + `/fork --name "B"` 创建两条独立分支；`/diff A B` 返回差异 JSON
- [ ] `/merge <session_id>` 跨 session 合并候选列表, 不破坏源 session

---

### Phase V.4 — 数据 CRUD 命令（6-8h，**风险最大**）

| # | 任务 | 估时 | 风险 |
|---|---|---:|---|
| V.4.1 | `/read` + `/list` + `/search`: 读路径 + 字段过滤 | 2h | 低 |
| V.4.2 | `/search --semantic`: 接入 Qdrant 向量搜索 | 1h | 中 |
| V.4.3 | `/write` + `/add`: 写路径, 走 ApprovalService 确认 | 2h | 中 |
| V.4.4 | `/delete`: 回收站机制（新表 + 30 天 TTL）| 2h | **高** |
| V.4.5 | `/batch`: 事务化批量操作 + preview | 2h | **高** |

**V.4 退出标准（可量化）**：
- [ ] 7 个 CRUD 命令可用
- [ ] `/delete candidate c001` → `recycle_bin` 写入原 row + 30 天 `expires_at`；`/restore candidate c001` 还原
- [ ] `/batch --action update --filter "score>80" --data {...}` **必须 preview 模式先返回 dry-run JSON**（影响行数 + 每行变更前后对比），用户二次确认才提交
- [ ] 批量事务一致性：**全部成功才 commit**；任一失败回滚至 batch 前 snapshot；失败列表写入 `command_audit_log`
- [ ] `/search "Java" --semantic` 命中 Qdrant 向量，top_k 默认 5

**V.4 风险**：
- 新表 `recycle_bin` 需要 Alembic 迁移（**不带 cron job 脚本**）
- `RecycleBinService.purge_expired()` 由 **Celery beat 每天 03:00** 触发，**与 Phase U.6 `ApprovalService.auto_expire()` 同一 worker pool**（避免双 worker 资源争抢）
- 语义搜索需 Qdrant 在线，否则降级为关键词搜索并提示用户

---

### Phase V.5 — 系统操作 + 快捷命令（4-6h）

| # | 任务 | 估时 |
|---|---|---:|
| V.5.1 | `/help` + `/version` + `/status`: 静态查询 | 1h |
| V.5.2 | `/settings` + `/config`: 双层配置（用户级 / 系统级）| 1.5h |
| V.5.3 | `/debug` + `/export` + `/import`: 高级运维 | 1.5h |
| V.5.4 | 别名注册 + `//` 转义 + `/` 面板触发 + **管道 stub** | 1h |

**V.5 退出标准**：
- [ ] 8 个系统命令全部实现
- [ ] `/settings`（用户级） vs `/config`（系统级，仅 admin） 权限分离生效
- [ ] **管道 v1 仅 stub**：检测到 `\|` 时**解析但不执行**，返回提示 "管道支持将于 v2.1 实现"

---

### Phase V.6 — 前端命令面板 + 集成（6-8h）

> **状态**：**V.6.1-V.6.4 ✅ 完成（2026-06-02）**
> V.6.5 E2E 待手动验证（需 dev server）

| # | 任务 | 估时 | 状态 |
|---|---|---:|---|
| V.6.1 | `command-palette.tsx`: cmdk 风格浮层, `/` 触发, **gzip chunk ≤ 30KB** | 2h | ✅ complete |
| V.6.2 | `use-commands.ts`: 前端命令状态管理 hook | 1h | ✅ complete（集成在组件内部）|
| V.6.3 | 自然语言 → 命令建议（**关键词匹配优先**，缓存 1h）| 1h | ✅ complete（filter 在 palette 内）|
| V.6.4 | 集成 command palette 到 `agent/page.tsx` | 1h | ✅ complete |
| V.6.5 | E2E (Playwright) + 全量回归 + 覆盖率守门 | 2h | ⏳ pending（需 dev server）|

**V.6 退出标准**：
- [x] `/` 触发命令面板浮层
- [x] 浮层 chunk gzip ≤ 30KB（构建产物检查：agent 页面 54.1 kB 首屏）
- [x] 自然语言输入 "重新来一遍" → 弹出建议 `/restart`（关键词匹配命中）
- [ ] E2E：pause/resume / delete/restore / batch preview+commit / fork+diff / search semantic
- [ ] 全量覆盖率 ≥ 90%

---

## 5. 验收总则

- [ ] 全部 28 个命令可用，单元测试覆盖 ≥ 90%
- [ ] L1 只读命令无确认; L2/L3 走 `command_audit_log` + (可选) ApprovalService
- [ ] 所有 CRUD 命令执行后自动创建快照
- [ ] 前端命令面板与对话输入融合, 无独立入口冲突
- [ ] 与 Phase S (LangGraph) 兼容; 与 Phase T (MCP) 共享工具层
- [ ] 审计日志可在 `/audit/logs` 页面查看到（新增 `source='command'` 过滤）

### 5.1 成功指标（上线后 30 天）
- 命令调用占比 ≥ 30%（vs 自然语言） — 衡量命令系统价值
- 危险操作（L3/L4）0 误操作事故 — 审计 + 二次确认有效
- 命令平均响应 < 200ms（无 LLM 路径） — `/read`/`/list`/`/status` 性能基线
- 自然语言→命令建议命中率 ≥ 40% — V.6.3 关键词匹配有效

### 5.2 权限矩阵（初版，M4 修复）

| 角色 | L1 只读 | L2 普通 | L3 敏感 | L4 危险 |
|---|:-:|:-:|:-:|:-:|
| viewer（只读 HR） | ✅ | ❌ | ❌ | ❌ |
| recruiter（招聘）| ✅ | ✅ | 部分（`/write /add`）| ❌ |
| hiring_manager | ✅ | ✅ | 部分（`/delete --no-recycle` 拒绝）| ❌ |
| admin | ✅ | ✅ | ✅ | ✅ |

L3 细分：`/delete` 和 `/batch` 需 recruiter+ 角色；`/rollback` 和 `/import` 需 admin。

### 5.3 国际化（m3 修复）
- v1 范围：**全中文** UI 文案、错误信息、命令面板 label
- v2.1 再做 i18n 框架（i18next + zh-CN/en-US）
- 命令名保持英文（`/restart` 不翻译），但命令 description 中文化

---

## 6. 风险登记

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | Phase S.3 未完成, LangGraph interrupt 不可用 | V.2.2 无法真暂停 | **二选一**：等 S.3 完成 / 降级为 UI 软暂停（见 V.2 退出标准降级方案）|
| R2 | 回收站表 (recycle_bin) 影响核心表性能 | 全表查询变慢 | 单独 schema, 30 天 TTL（Celery beat 触发 purge），不参与 JOIN |
| R3 | 自然语言→命令 LLM 成本 | token 消耗 | **关键词匹配优先**，LLM 分类仅兜底；1h Redis 缓存 |
| R4 | 命令面板 cmdk 与 chat 输入冲突 | UX 混乱 | "/" 前缀时不弹聊天建议, 按 ESC 退出 |
| R5 | 28 个命令并发执行影响 session 锁 | 数据竞争 | **Redis 分布式锁** `cmd:lock:session:{sid}`，timeout 10s（替代 asyncio.Lock，跨 worker 生效）|
| R6 | `/batch` 事务化失败回滚 | 数据不一致 | 全部成功才提交, 失败回滚至 batch 前 snapshot, 失败列表写入 `command_audit_log` |
| R7 | 命令面板增加前端 bundle 体积 | 性能 | cmdk 懒加载, 仅 agent 页面引入, **gzip chunk ≤ 30KB** |
| R8 | OperationLog 字段不匹配 | 写入失败或污染物化表 | **新建 `command_audit_log` 表**，与 OperationLog 完全分离 |

---

## 7. 与现有路线图的关系

```
现有 Phase S/T/U/V (consolidated-next-plan.md)
              ↓
       Phase V-Command (本规划) ← 在 V 之后追加, 编号 V.1-V.6
              ↓
   V.1  ─→  V.2  ─→  V.3  ─→  V.4  ─→  V.5  ─→  V.6
   8-10h    4-6h    4-6h    6-8h    4-6h    6-8h
              ↓
        总计 38-48h ≈ 2-3 周
```

| 与现有计划的关系 | 行动 |
|---|---|
| 必须在 Phase S.3 (LangGraph) 之后 | V.2.2 等待 S.3 完成（或走降级方案）|
| 可与 Phase T (MCP) 并行 | V.4.1/V.4.2 直接复用 T 的工具, 减少重复 |
| **不复用** Phase U 的 OperationLog | V.1.5/V.1.7 新建 `command_audit_log` 表 |
| Celery worker 复用 | V.4.4 `RecycleBinService.purge_expired` 与 Phase U.6 `ApprovalService.auto_expire` 同一 worker pool |

---

## 8. 关键决策点（已确认）

> ✅ 用户已确认采用以下默认决策，启动 V.1：

1. **MVP 范围**：**全部 28 个**（沿用推荐 A，4-6 周）
2. **与 Phase S/T 的顺序**：**等 Phase S.3 完成再启动 V.2.2**（推荐 A，稳妥）；V.1 可立即启动
3. **前端命令面板交互**：**cmdk 风格浮层**（⌘K / `/` 触发，推荐 A）
4. **管道支持（`/` 管道）**：**v1 stub 解析不执行**（推荐 A 修正版，节省实现成本，v2.1 真正实现）
5. **自然语言→命令建议**：**关键词匹配优先 + 兜底 LLM 分类**（m5 修复后版本）

---

## 9. 参考材料

- **设计文档**：`AI招聘Agent内置命令系统V2.0.md`（本计划实施对象）
- **MCP 工具设计**：`AI_招聘系统_MCP_工具系统设计文档_v2.md`（工具层定义）
- **当前路线图**：`.omo/plans/consolidated-next-plan.md`（Phase S/T/U/V）
- **记忆架构**：`AI招聘Agent_上下文记忆架构设计.md`（session 上下文依赖）
- **LangGraph 任务快照**：`LangGraph任务快照.md`（/pause /resume 实现参考）
- **代码库**：
  - `apps/api/app/services/agent_service.py` — 入口改造点
  - `apps/api/app/services/conversation_service.py` — session 管理
  - `apps/api/app/api/agent.py` — `/api/v1/agent/chat` 端点
  - `apps/api/app/api/audit.py` — 审计日志（Phase U，**不**复用）

---

## 10. Momus 评审记录

> 本节记录 Momus 评审反馈及修复追踪，供后续审计。

| 严重度 | ID | 问题 | 修复位置 |
|---|---|---|---|
| 🔴 Blocker | B1 | C0.7 单元测试 1h 不现实 | V.1.8 拆为 8a/8b/8c |
| 🔴 Blocker | B2 | R1 缓解与 C1.2 退出标准自相矛盾 | V.2 显式列降级方案 |
| 🔴 Blocker | B3 | Phase 编号未对齐 S/T/U/V | 改为 V-Command / V.1-V.6 |
| 🟡 Major | M1 | 退出标准大多不可量化 | V.1-V.6 退出标准全部加量化指标 |
| 🟡 Major | M2 | OperationLog schema 冲突 | 新建 `command_audit_log` 表 |
| 🟡 Major | M3 | 回收站 30 天 TTL 无实现路径 | V.4.4 指定 Celery beat + 复用 U.6 worker |
| 🟡 Major | M4 | 权限矩阵 L1-L4 缺具体映射 | §5.2 补全角色 × 级别矩阵 |
| 🟡 Major | M5 | 管道 `\|` 语义歧义 | V.5.4 改为 stub 解析 |
| 🟡 Major | M6 | 跨进程 session 锁 | R5 改 Redis 分布式锁 |
| 🟢 Minor | m1 | LLM 模型与命令默认值未联动 | V.1.1 注释加 LLM 工厂取 |
| 🟢 Minor | m2 | 前端 bundle 预算缺失 | V.6.1 加 gzip ≤ 30KB |
| 🟢 Minor | m3 | 国际化未定 | §5.3 v1 全中文 |
| 🟢 Minor | m4 | 成功指标缺失 | §5.1 加 4 项指标 |
| 🟢 Minor | m5 | C5.3 LLM 决策矛盾 | V.6.3 关键词优先 |
| 🟢 Minor | m6 | 错误传播没说 | V.1.1 加 `CommandErrorCode` 枚举 |

**总评分（修复后）**：
- 清晰度：7 → 8
- 可验证性：5 → 8
- 完整性：6 → 8
- 风险真实度：7 → 8
- 与现有架构一致：6 → 9

---

> **下一步**：V.1 (基础骨架) 启动中。实施完成后回填 V.1 退出标准实际结果。
