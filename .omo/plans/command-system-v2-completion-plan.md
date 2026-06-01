# Command System V2.0 — 收尾计划 (2026-06-02)

> 本计划覆盖 Command System V2.0 集成后的剩余收尾工作。
> 所有新计划必须写入 `.omo/plans/*.md`。

---

## 剩余任务

| # | 任务 | 文件 | 状态 |
|---|---|---|---|
| C.1 | 运行命令测试 `pytest tests/test_commands/ -q` | `apps/api/tests/test_commands/` | ⏳ pending |
| C.2 | 提交所有未 commit 变更 | 全部 | ⏳ pending |
| C.3 | E2E 验证（需要 dev server） | — | ⏳ pending (blocked: 需要启动服务) |

---

## C.1 — 运行命令测试

```bash
cd apps/api && python -m pytest tests/test_commands/ -q
```

**预期**：全部通过（31 个命令的单元测试）

**如果失败**：
- 检查 `registry.py` 的 `get_default_registry()` 是否正确注册
- 检查 `permissions.py` 的 `role_to_permissions()` 是否正确映射
- 检查 `CommandContext` 构造是否完整

---

## C.2 — 提交所有变更

**未提交文件**（git status）：

```
?? 新增文件：
  - apps/api/app/commands/           (31 命令实现)
  - apps/api/app/tools/candidate.py, job.py, evaluation.py, ...
  - apps/api/app/core/context_builder.py
  - apps/api/app/core/prompts.py
  - apps/api/app/models/command_audit_log.py
  - apps/api/alembic/versions/c0a1f3b8e2d4_add_command_audit_log.py
  - apps/api/tests/test_commands/
  - apps/web/e2e/agent-operation-panel.spec.ts
  - apps/web/hooks/useResumeUpload.ts
  - .omo/plans/command-system-v2-plan.md

 M 修改文件：
  - apps/api/app/api/agent.py        (CommandContext 集成)
  - apps/api/app/core/dependencies.py (get_current_user)
  - apps/api/app/services/agent_service.py (命令检测 + needs_human)
  - apps/web/app/(dashboard)/agent/page.tsx (needsHuman state)
  - apps/web/components/features/chat/OperationPanel.tsx (amber banner)
```

**Commit 消息**：

```
feat(commands): add Command System V2.0 — 31 commands with permission model

- CommandExecutor with role-based permissions (L1-L4)
- /add /back /batch /cancel /checkpoint /clear /config /debug
  /delete /diff /export /fork /help /history /import /list /merge
  /new /pause /read /restart /resume /retry /rollback /search
  /settings /snapshot /status /switch /version /write
- get_current_user() returns {user_id, role} from JWT
- role_to_permissions() maps viewer→L1, recruiter/hiring_manager→L1+L2+L3, admin/owner→L1-L4
- agent_service: /command short-circuits LLM path, returns directly
- needs_human escalation banner in OperationPanel (amber warning)
- CommandAuditLog model for command execution audit trail
```

---

## C.3 — E2E 验证（需要运行服务）

### 前提条件
```bash
docker compose up -d postgres redis qdrant minio
cd apps/api && uvicorn app.main:app --reload --port 8000 &
cd apps/web && pnpm dev &
```

### 测试用例

| 用例 | 操作 | 预期结果 |
|---|---|---|
| E2E.1 | `POST /api/v1/agent/chat` 发 `/help` | 直接返回 help 文本，不走 LLM |
| E2E.2 | `POST /api/v1/agent/chat` 发 `帮我看看有哪些候选人` | 走 AI 对话路径，正常回复 |
| E2E.3 | 上传简历 → AI 解析失败 → 弹出 OperationPanel | amber banner 可见 |
| E2E.4 | viewer 角色发 `/write` 命令 | 权限不足，返回错误 |

---

## 退出标准

- [ ] C.1: `pytest tests/test_commands/ -q` 全部通过
- [ ] C.2: 所有变更已 commit，git status 干净
- [ ] C.3: E2E 测试手动完成（或 CI 环境验证）

---

## 参考文档

- `AI_招聘系统_MCP_工具系统设计文档_v2.md` — 命令系统 V2 设计
- `apps/api/app/commands/` — 31 个命令实现
- `apps/api/app/commands/registry.py` — `get_default_registry()`
- `apps/api/app/commands/permissions.py` — `role_to_permissions()`
