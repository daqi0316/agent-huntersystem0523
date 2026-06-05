# P5-1 多租户 实施 PR 拆分 (3 周 15.5d → 10 PR)

> spec: `docs/multi-tenant-design.md`
> 配套:roadmap `docs/roadmap-2026-h2.md` §1.1 P5-1

## 0. 总览

| # | PR | 天 | 依赖 | 风险 |
|---|---|---|---|---|
| 1 | Org/Member/Invitation/User models + Alembic | 2d | - | 低 |
| 2 | 25+ 表加 org_id + RLS policy + 索引 (含 CONCURRENTLY) | 2d | PR 1 | 中 (大表锁) |
| 3 | 中间件 (transaction + get_org_context + auto_create_default_org) | 2d | PR 2 | 低 |
| 4 | admin role (BYPASSRLS) + admin_db engine | 0.5d | PR 1 | 低 |
| 5 | endpoint 改造 batch 1 (/candidates + /jobs) | 1d | PR 3 | 低 |
| 6 | endpoint 改造 batch 2 (/applications + /interviews + /evaluations) | 1d | PR 5 | 低 |
| 7 | endpoint 改造 batch 3 (/agent + /human-loop + /auth/me) | 1d | PR 5,6 | 中 (SSE 切换) |
| 8 | 老数据迁移 (default org + 老用户 + 通知) | 1d | PR 1,3 | 中 (大表) |
| 9 | /auth/switch-org + JWT claim + 前端 AuthContext | 2d | PR 7,8 | 中 (SSE 重连) |
| 10 | 跨租户测试 + E2E 改造 + perf benchmark + 文档 | 3d | PR 9 | 高 (CI gate) |

**合计**: 15.5d = 3 周 (10 PR)

每个 PR 完成后, 跑 health-check + 单独 commit + 单独 push, 不积压。

---

## 1. PR 1: 数据模型 (D1-2)

**目标**: 4 张新表 + Alembic migration

### 1.1 文件
- `apps/api/app/models/organization.py` (新)
- `apps/api/app/models/membership.py` (新)
- `apps/api/app/models/invitation.py` (新)
- `apps/api/app/models/user.py` (加 `is_platform_admin` 字段)
- `apps/api/app/models/__init__.py` (注册)
- `alembic/versions/xxxx_create_org_tables.py` (新)

### 1.2 schema 摘要
见 spec §2.1-2.4。

### 1.3 验收
- [ ] `alembic upgrade head` 跑通, 4 表创建
- [ ] `alembic downgrade base` 跑通, 4 表删除
- [ ] unit test: 创建/查询 Organization / Membership / Invitation / User
- [ ] tsc 0 错
- [ ] health-check 9/0

### 1.4 commit message
```
feat(api): P5-1 PR 1 — Organization / Membership / User / Invitation models

数据模型层 (不含 RLS / endpoint 改造)。

- 4 张新表 schema + Alembic migration
- User 加 is_platform_admin (admin bypass 用)
- downgrade 完整可逆

验收: pytest 4/4 + alembic upgrade/downgrade + health 9/0
```

---

## 2. PR 2: 25+ 表加 org_id + RLS + 索引 (D2-3)

**目标**: 业务表加 org_id 列 + RLS policy + 索引 (大表 CONCURRENTLY)

### 2.1 文件
- `alembic/versions/xxxx_add_org_id_candidate.py` (小表)
- `alembic/versions/xxxx_add_org_id_audit_log.py` (大表, CONCURRENTLY)
- `alembic/versions/xxxx_enable_rls.py`
- `apps/api/app/core/rls.py` (policy 模板)

### 2.2 关键决策 (Momus P0-3)
- **小表 (job/candidate/application/...)**: 一次性 migration, `ADD COLUMN org_id UUID NOT NULL DEFAULT '00000000...'`
- **大表 (audit_log/notification/...)**: 分文件, `op.execute("COMMIT")` + `CREATE INDEX CONCURRENTLY`
- **每个表独立 migration** (一个表一个文件), 方便回滚

### 2.3 RLS policy 模板 (见 spec §3.1)
```sql
CREATE POLICY org_isolation ON {table}
  USING (
    org_id = COALESCE(
      NULLIF(current_setting('app.current_org_id', true), ''),
      '00000000-0000-0000-0000-000000000000'
    )::uuid
  );
```

### 2.4 验收
- [ ] 25+ 表 `org_id` 列存在
- [ ] 25+ 表 RLS 启用 + FORCE
- [ ] 25+ policy 创建
- [ ] 大表 (audit_log) `CREATE INDEX CONCURRENTLY` 跑通
- [ ] 直接 query `SELECT * FROM candidate` (无 SET LOCAL) → 返 default org 数据 (P0-1)
- [ ] tsc 0 错
- [ ] health-check 9/0

### 2.5 风险 + 缓解
- **大表 lock**: 分批部署, 先 staging 跑一次, 监控 lock 时间 < 30s
- **RLS 默认 deny**: 如果某表忘加 policy,所有 query 返 0 行 → 测试要 cover

---

## 3. PR 3: 中间件 (D3-4)

**目标**: 3 个核心中间件

### 3.1 文件
- `apps/api/app/core/database.py` (加 `get_db_with_transaction`)
- `apps/api/app/core/org_context.py` (新, `get_org_context`)
- `apps/api/app/core/auto_org.py` (新, `get_or_create_default_org`)

### 3.2 代码骨架 (见 spec §3.2)
```python
# database.py
@asynccontextmanager
async def get_db_with_transaction():
    async with async_session() as session:
        async with session.begin():
            yield session

# org_context.py
async def get_org_context(
    user = Depends(get_current_user),
    db = Depends(get_db_with_transaction),
) -> OrgContext:
    org_id = ...  # JWT claim
    # membership check
    # SET LOCAL
    return OrgContext(...)

# auto_org.py
async def get_or_create_default_org(user, db):
    # P0-5 修法, E2E 透明
```

### 3.3 验收
- [ ] 3 个中间件实现
- [ ] 单元测试 5/5 (含 membership check fail 抛 403)
- [ ] tsc 0 错
- [ ] health-check 9/0

---

## 4. PR 4: admin role + admin_db (D5)

**目标**: `airecruit_admin` BYPASSRLS role + admin engine

### 4.1 文件
- `alembic/versions/xxxx_create_admin_role.py`
- `apps/api/app/core/admin_db.py` (新)
- `apps/api/.env.example` (加 `DATABASE_URL_ADMIN`)

### 4.2 SQL (见 spec §3.3.1)
```sql
CREATE ROLE airecruit_admin BYPASSRLS;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO airecruit_admin;
```

### 4.3 验收
- [ ] role 创建跑通
- [ ] admin engine 连接测试
- [ ] 用 admin engine query 25+ 表, 不受 RLS 限制
- [ ] tsc 0 错
- [ ] health-check 9/0

---

## 5. PR 5: endpoint 改造 batch 1 — /candidates + /jobs (D6)

**目标**: 高频核心 endpoint 走 `get_org_context`

### 5.1 文件
- `apps/api/app/api/candidates.py` (加 `Depends(get_org_context)`)
- `apps/api/app/api/jobs.py` (同)
- `apps/api/app/api/router.py` (无变动)

### 5.2 改造模式
```python
# 之前
@router.get("/candidates")
async def list_candidates(db: AsyncSession = Depends(get_db)):
    return await db.execute(select(Candidate))

# 之后
@router.get("/candidates")
async def list_candidates(
    org_ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db_with_transaction),
):
    # org_ctx 自动 SET LOCAL, RLS 生效
    return await db.execute(select(Candidate))
```

### 5.3 验收
- [ ] /candidates 走 get_org_context
- [ ] /jobs 走 get_org_context
- [ ] 单测: 不同 user 只能看自己 org 数据
- [ ] 现有 e2e verify-t4-detail 9/9 重跑 pass (因 P0-5 auto_create_default_org, 透明)
- [ ] tsc 0 错
- [ ] health-check 9/0

### 5.4 工时注
- 每个 endpoint ~30min
- 2 个 = 1d
- 跨租户 negative test 5/5 (含 SQL injection bypass 尝试)

---

## 6. PR 6: endpoint 改造 batch 2 — /applications + /interviews + /evaluations (D7)

**目标**: 中频业务 endpoint

### 6.1 文件
- `apps/api/app/api/applications.py`
- `apps/api/app/api/interviews.py`
- `apps/api/app/api/evaluations.py`

### 6.2 验收
- [ ] 3 个 endpoint 走 get_org_context
- [ ] 单测 + 跨租户 negative test
- [ ] tsc 0 错
- [ ] health-check 9/0

---

## 7. PR 7: endpoint 改造 batch 3 — /agent + /human-loop + /auth/me (D7)

**目标**: AI 核心 endpoint (含 SSE 流)

### 7.1 文件
- `apps/api/app/api/agent.py`
- `apps/api/app/api/agent_events.py` (SSE, P0-4 重点)
- `apps/api/app/api/human_loop.py`
- `apps/api/app/api/auth.py` (改 /auth/me 返回 memberships)

### 7.2 SSE 切换处理 (Momus P0-4)
- `/auth/switch-org` 返回新 JWT
- 前端 close 当前 SSE → 用新 JWT 重连
- 服务端: SSE 关闭时清 last_event_id 缓存 (per user + per org)

### 7.3 验收
- [ ] 4 个 endpoint 走 get_org_context
- [ ] /auth/me 返回 memberships + current_org
- [ ] SSE 切换: 关闭 + 重连 + 漏单 0
- [ ] tsc 0 错
- [ ] health-check 9/0

---

## 8. PR 8: 老数据迁移 (D8)

**目标**: default org 自动建 + 老用户加 owner + 25+ 表数据迁移 + 通知

### 8.1 文件
- `alembic/versions/xxxx_backfill_default_org.py` (新, 数据迁移)
- `apps/api/app/api/notifications.py` (加 onboarding 站内信)
- `apps/api/tests/test_migration.py` (迁移测试)

### 8.2 迁移逻辑 (见 spec §6)
```python
# 1. 建 default org (id = 00000000-...)
# 2. 所有 user → default org owner
# 3. 所有业务数据 → default org
# 4. 通知现有用户
```

### 8.3 验收
- [ ] 迁移跑通
- [ ] 老用户数据 100% 保留 (无丢失)
- [ ] 25+ 表行数对比 (迁移前 = 迁移后)
- [ ] 通知发送
- [ ] tsc 0 错
- [ ] health-check 9/0

---

## 9. PR 9: /auth/switch-org + JWT + 前端 (D9-10)

**目标**: 用户切换 org 流程完整

### 9.1 文件
- `apps/api/app/api/auth.py` (加 `/auth/switch-org`)
- `apps/api/app/core/jwt.py` (claim 含 `current_org_id`)
- `apps/web/lib/auth-context.tsx` (多 org 切换 UI)
- `apps/web/app/(dashboard)/org-switcher.tsx` (新组件)
- `apps/web/app/(dashboard)/layout.tsx` (集成)

### 9.2 流程 (Momus P0-4)
```
1. Client → POST /auth/switch-org {org_id} (带 OLD_JWT)
2. Server 验证 membership → 签 NEW_JWT (含 new current_org_id)
3. Server → {access_token: NEW_JWT, expires_in: 3600}
4. Client: 替换 localStorage + axios header
5. SSE 重连 (用 NEW_JWT)
```

### 9.3 验收
- [ ] /auth/switch-org 跑通
- [ ] JWT 含 current_org_id claim
- [ ] 前端 OrgSwitcher 组件可见可点
- [ ] 切换后 100ms 内新 query 走新 org
- [ ] SSE 重连 0 漏单
- [ ] tsc 0 错
- [ ] health-check 9/0

---

## 10. PR 10: 跨租户测试 + E2E + 性能 (D11-12)

**目标**: CI gate + 全 e2e pass + perf baseline 通过

### 10.1 文件
- `apps/api/tests/test_multi_tenant.py` (10 跨租户 negative test)
- `apps/api/tests/test_rls.py` (RLS 边界, 含 SQL injection)
- `apps/api/tests/test_perf.py` (perf benchmark 自动化)
- `docs/multi-tenant-runbook.md` (部署 + 排错 SOP)

### 10.2 测试清单 (见 spec §5.2)
```
- [ ] test_user_cannot_see_other_org_candidates
- [ ] test_user_cannot_see_other_org_jobs
- [ ] test_user_cannot_see_other_org_applications
- [ ] test_user_cannot_see_other_org_evaluations
- [ ] test_user_cannot_see_other_org_interviews
- [ ] test_user_cannot_modify_other_org_data
- [ ] test_user_cannot_delete_other_org_data
- [ ] test_sql_injection_cannot_bypass_rls
- [ ] test_platform_admin_bypass_works
- [ ] test_cross_org_aggregate_uses_explicit_bypass
```

### 10.3 E2E 改造 (P0-5)
- `auto_create_default_org` 中间件, E2E 注入 token 后自动建 default org
- 所有 26 个 e2e 重跑 (verify-t2/t4/t5/t6/t7/mobile)
- 至少 90% pass (4-5 个会因为 token claim 调整需微调)

### 10.4 perf benchmark
- 跑前: p99 baseline (D0)
- 跑后: p99 (D12)
- 增量 < 10% 算 pass

### 10.5 验收 (CI gate)
- [ ] 10/10 跨租户 negative test
- [ ] 25+ e2e 重跑 ≥ 90% pass
- [ ] perf p99 增量 < 10%
- [ ] 文档: 多租户部署 SOP + 排错 runbook
- [ ] tsc 0 错
- [ ] health-check 9/0

---

## 11. 实施时间表 (建议)

| Day | 上午 | 下午 | commit 数 |
|---|---|---|---|
| 1 (D1) | PR 1 models | PR 1 migration + test | 1 |
| 2 (D2) | PR 2 25+ 表小表 migration | PR 2 大表 CONCURRENTLY + RLS | 1 |
| 3 (D3) | PR 3 database 包装 | PR 3 org_context + auto_org | 1 |
| 4 (D4) | PR 4 admin role | PR 5 /candidates + /jobs | 2 |
| 5 (D5) | PR 6 /applications /interviews /evaluations | PR 7 /agent /human_loop /auth/me | 2 |
| 6 (D6) | PR 8 老数据迁移 + 通知 | PR 8 测试 | 1 |
| 7 (D7) | PR 9 /auth/switch-org | PR 9 JWT claim + 前端 | 1 |
| 8 (D8) | PR 9 前端 OrgSwitcher 组件 | PR 10 跨租户 10/10 test | 1 |
| 9 (D9) | PR 10 e2e 改造 (auto_create_default_org) | PR 10 e2e 重跑 | 1 |
| 10 (D10) | PR 10 perf benchmark | PR 10 文档 + 收尾 | 1 |
| 11 (D11) | buffer (修 PR review 反馈) | buffer | 0-2 |
| 12 (D12) | buffer / 性能调优 | buffer / 文档 | 0-1 |

**11 个 commit** (主流程) + 0-3 个 fixup (review 反馈)

**P5-1 完结后**: 立刻接 P5-2 (Team 管理) / P5-3 (国内支付) / P5-4 (个保法) 等 Phase 5 后续任务。

---

## 12. 每个 PR 共用 checklist (DoD)

每个 PR 合并前必过:
- [ ] `npx tsc --noEmit` 0 错 (apps/web)
- [ ] `python -m pytest apps/api/tests/ -x` 全过
- [ ] `bash scripts/health-check.sh` 9/0
- [ ] 自己写新单测 (覆盖新代码)
- [ ] 现有 e2e 不破 (至少关键 5 个跑过)
- [ ] commit message 含中文引号时用 `git commit -F /tmp/x.md` (file-based)
- [ ] PR description 引用 spec 章节 (e.g. "P5-1 PR 5, see spec §3.2")

---

## 13. 风险 + 缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| PR 2 大表 lock 太久 | 中 | P0 | staging 先跑一次, 监控 lock_time; 不超过 30s 才上 prod |
| PR 5/6/7 endpoint 漏改, 某表忘 RLS | 中 | 数据泄漏 | CI gate 跨租户 test + admin path query 25+ 表 |
| PR 8 老数据迁移丢数据 | 低 | 致命 | 迁移前 dump + 迁移后 25+ 表行数对比 + audit_log 验证 |
| PR 9 SSE 重连漏单 | 中 | 体验 | Last-Event-ID 持久化 (T3 已做), 重连用 old cursor |
| PR 10 perf p99 超 10% | 低 | 中 | 索引 review + EXPLAIN ANALYZE + 加 `org_id` 复合索引 |

---

## 14. 关联文档

- `docs/multi-tenant-design.md` (spec, 9.5/10)
- `docs/roadmap-2026-h2.md` (路线图, Phase 5 §1.1 P5-1)
- `docs/lessons-learned.md` (历史教训, 实施时参考)
- `docs/error-handling-matrix.md` (RLS fail 行为 §5)

---

## 15. 一句话总结

> P5-1 = 10 PR, 15.5 天, 3 周。
> 顺序: 数据模型 → RLS → 中间件 → admin → endpoint (3 batch) → 老数据 → auth → 测试。
> 每个 PR 独立 commit + push, 跑 health-check 9/0, 不积压。
