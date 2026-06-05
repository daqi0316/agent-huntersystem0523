# P5-1 补救计划 — 3 P0 + 3 P1 修复方案

更新时间: 2026-06-05
触发: Momus 替代评审 (7.0/10, 3 P0 阻断 ship)

## 目标
把 P5-1 多租户改造从"7.0/10 自我评价"提升到 "9.0+/10 真实完成"。

## 范围 (3 P0 + 3 P1)

### P0-1: e2e 改造 (1-2 天)

**现状**: 18 现有 e2e 脚本未适配 current_org_id, 跑全量 e2e 必大面积失败。

**任务清单**:
1. 列所有 e2e 脚本 (`apps/web/scripts/verify-*.ts`)
2. 给测试登录响应加 `current_org_id` 自动提取 (verify-helpers)
3. 所有 fetch 调用统一加 `X-Org-Id` header
4. 跑全量 e2e, 记录失败 → 就地修
5. 写 regression summary: 修复前 X 失败, 修复后 0 失败

**成功标准**:
- 全量 e2e 跑一次, 0 失败
- 新加的 X-Org-Id helper 写进 e2e-setup.ts 共享

**影响文件**:
- `apps/web/scripts/verify-*.ts` (18 文件)
- `apps/web/scripts/verify-helpers.ts` (新建)
- `apps/web/e2e-setup.ts` (新建)

### P0-2: audit log API (1 天)

**现状**: audit_log 表有 (PR 2), 但 switch-org 中间件没落库, GET /audit-logs endpoint 没写。

**任务清单**:
1. Pydantic schema: `AuditLogOut`, `AuditLogList`
2. API: `GET /audit-logs` (org-scoped, 当前 token 用户的 org)
3. 中间件 hook: `apply_audit_log` 在 switch-org / invite-accept / membership-change 时落库
4. 单测: audit_log 写入 + 查询 org 隔离

**成功标准**:
- switch-org 后 audit_log 有新行
- GET /audit-logs 返 org 内日志, RLS 隔离生效
- 3 单测 pass (写入 + 查询 + 跨 org 隔离)

**影响文件**:
- `apps/api/app/schemas/audit_log.py` (新建)
- `apps/api/app/api/audit_logs.py` (新建)
- `apps/api/app/api/router.py` (注册)
- `apps/api/app/core/org_context.py` (加 hook)
- `apps/api/tests/test_audit_logs.py` (新建)

### P0-3: DB-level 测试 fix (1 天)

**现状**: PR 8 / PR 10 / P5-2 invitations 三次写 DB-level 单测都失败, 根因未找。

**根因假设** (待验证):
- conftest fixture 依赖图: arecruit_app role setup 顺序不对
- transaction rollback 时 audit_log (新表) 还没建
- 异步 session 关闭时机问题

**任务清单**:
1. 读 `tests/conftest.py` + 4 个 test 文件, 画依赖图
2. 写 minimal reproducer (1 test, 1 query) 找根因
3. 修 conftest 或 test fixture
4. 写 `test_cross_tenant_isolation_enforced.py` (1 个独立 dedicated negative test)
5. 跑全部 22 + 新 1 + audit_log 3 = 26 单测

**成功标准**:
- 1 个独立 dedicated cross-tenant negative test 真过
- 26 单测全 pass (P5-1 22 + audit_log 3 + new 1)
- 根因写进 lessons-learned.md

**影响文件**:
- `apps/api/tests/conftest.py` (改)
- `apps/api/tests/test_cross_tenant_isolation_enforced.py` (新建)
- `docs/lessons-learned.md` (加 P5-1 教训章节)

### P1-1: 跑全量 e2e 一次 + 写结果
- 接 P0-1, 修完跑, 结果写进 `docs/p5-1-completion.md`

### P1-2: 修 docs/p5-1-completion.md 漏报
- 显式标 e2e 改造 + audit log 状态 (从 P5-2 推 → 已完成)

### P1-3: commit ec9a836 撤回 test 不专业
- 用 `git reset --soft HEAD~1` 合并到 eae52ae, 或 fixup squash
- 保持 9 PRs + closure 风格一致

## 工期估算
- P0-1: 1-2 天
- P0-2: 1 天
- P0-3: 1 天 (含根因调研)
- P1-1+2+3: 0.5 天
- **总计: 3.5-4.5 天**

## 验收 (修复完成定义)
- [ ] P0-1/2/3 全过
- [ ] P1-1/2/3 全过
- [ ] health-check.sh 9/0 pass
- [ ] tsc 0 错
- [ ] 全量 e2e 跑一次 + 0 失败
- [ ] 26 单测全 pass
- [ ] 4 commit (每 P0 一 commit) + 1 doc commit
- [ ] push 全部成功
- [ ] 评分自评 ≥ 9.0/10

## 风险
- **网络 push 不可控** (今天已遇 2 次) → 批量 commit 后再 push
- **DB-level 测试根因可能更深** → 预留 1 天缓冲
- **18 e2e 脚本可能漏 1-2 个未跑过** → 全跑前先 audit 一遍
