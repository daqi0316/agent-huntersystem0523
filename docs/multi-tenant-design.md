# 多租户设计 Spec (Phase 5 P5-1)

> P5-1 实施前 spec,12 天工时的根。
> 配套:roadmap 2026-07 `docs/roadmap-2026-h2.md` §1.1。

## 1. 目标与范围

### 1.1 现状痛点
- 25+ 张业务表全部无 `org_id` 概念,所有 query 共享
- 单租户 = 单客户 = B2B 卖不动 (法务/采购/数据隔离都不通)
- 当前无 team / role,只有 user → 权限粗糙

### 1.2 设计目标
- **隔离 (P0)**: org A 用户**绝不可能**读到 org B 数据 (含 SQL 注入)
- **简洁**: 业务代码不显式传 org_id,由中间件自动注入
- **可测**: 跨租户 negative test 必过
- **性能**: RLS 开销 < 5% p99 latency

### 1.3 范围
- ✅ 25+ 业务表加 `org_id` NOT NULL + 索引 + 外键
- ✅ Postgres RLS 强制隔离
- ✅ 老数据迁移到 default org
- ✅ 跨租户测试 fixture
- ❌ cross-org 共享 (Phase 5 不做)
- ❌ org 层级 (parent/sub) (Phase 5 不做)
- ❌ 跨 org 聚合查询 (admin 后台单独 path,业务无)

---

## 2. 数据模型

### 2.1 organization

```python
class Organization(Base):
    __tablename__ = "organization"

    id: UUID (PK, default uuid4)
    slug: str (unique, indexed)  # URL 用,小写 + 数字
    name: str
    plan: Enum["starter", "pro", "enterprise"] (default "starter")
    status: Enum["active", "trial", "suspended", "deleted"] (default "trial")

    # Quota (per 月)
    quota_max_users: int (default 10)
    quota_max_candidates: int (default 1000)
    quota_max_storage_mb: int (default 5000)
    quota_llm_tokens_per_month: int (default 500_000)

    # 时间
    created_at, updated_at
    trial_ends_at: datetime | None
    subscription_renews_at: datetime | None
    deleted_at: datetime | None  # 软删 (GDPR 30 天宽限)

    # 设置
    settings: JSONB (default {})
```

### 2.2 membership (user ↔ org 多对多)

```python
class Membership(Base):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)

    id: UUID (PK)
    org_id: UUID (FK → organization, indexed)
    user_id: UUID (FK → user, indexed)
    role: Enum["owner", "hr", "viewer", "api"] (default "hr")
    status: Enum["active", "pending", "suspended"] (default "active")

    invited_by: UUID (FK → user) | None
    invited_at, joined_at, last_active_at
```

**角色矩阵** (Phase 5 简化版):
| role | 读 | 写候选人 | 审批 | 邀请 | 计费 |
|---|---|---|---|---|---|
| owner | ✓ | ✓ | ✓ | ✓ | ✓ |
| hr | ✓ | ✓ | ✓ | ✗ | ✗ |
| viewer | ✓ | ✗ | ✗ | ✗ | ✗ |
| api | ✓ (限) | ✗ | ✗ | ✗ | ✗ |

### 2.3 user (平台级身份)

```python
class User(Base):
    __tablename__ = "user"

    id: UUID (PK)
    email: str (unique, indexed)
    phone: str (unique, indexed, partial index)
    name: str
    password_hash: str | None  # 可空 (微信扫码登录无密码)
    avatar_url: str | None

    # 平台级
    is_platform_admin: bool (default False)  # 我们自己,绕 RLS
    status: Enum["active", "suspended", "deleted"]

    created_at, updated_at
    last_login_at
    deleted_at | None
```

### 2.4 invitation (邀请待接受)

```python
class Invitation(Base):
    __tablename__ = "invitation"

    id: UUID (PK)
    org_id: UUID (FK, indexed)
    email: str  # 受邀人邮箱
    role: Enum["owner", "hr", "viewer"]
    token: str (unique, indexed)  # 一次性
    invited_by: UUID (FK → user)
    invited_at, expires_at (默认 7 天)
    accepted_at | None
    status: Enum["pending", "accepted", "expired", "cancelled"]
```

---

## 3. Row-Level Security (RLS) 策略

### 3.1 Postgres RLS 启用

```sql
-- 每张业务表启用 RLS
ALTER TABLE candidate ENABLE ROW LEVEL SECURITY;
ALTER TABLE job ENABLE ROW LEVEL SECURITY;
-- ... 全部 25+ 张

-- 创建 policy
CREATE POLICY org_isolation ON candidate
  USING (org_id = current_setting('app.current_org_id', true)::uuid);

-- service role bypass (我们后台 admin 用)
ALTER TABLE candidate FORCE ROW LEVEL SECURITY;
-- 仍 bypass: 当前 user 是 superuser 或 BYPASSRLS
```

### 3.2 中间件注入 org context

FastAPI dependency:

```python
# apps/api/app/core/org_context.py
from sqlalchemy import text
from app.core.auth import get_current_user
from app.core.database import get_db

async def get_org_context(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgContext:
    # 1. 从 JWT / header 拿当前 org_id
    org_id = ...  # JWT claim 或 X-Org-Id header

    # 2. 验证 user 真的 belong 这个 org
    membership = await db.execute(
        select(Membership).where(
            Membership.org_id == org_id,
            Membership.user_id == user.id,
            Membership.status == "active",
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(403, "not a member of this org")

    # 3. SET LOCAL (per transaction) 让 RLS 谓词生效
    await db.execute(
        text("SET LOCAL app.current_org_id = :oid"),
        {"oid": str(org_id)}
    )

    return OrgContext(
        org_id=org_id,
        user_id=user.id,
        role=membership.role,
    )
```

### 3.3 RLS 边界

| 场景 | RLS 行为 |
|---|---|
| 业务 query (走 `Depends(get_org_context)`) | SET LOCAL 已设,policy 生效,只能看自己 org |
| Platform admin (我们) | `BYPASSRLS` role,绕 policy,看全部 |
| Alembic migration | superuser 绕 RLS,正常 |
| 跨 org aggregate (admin 后台) | 显式 `SET LOCAL app.bypass_rls = 'true'` |
| 单元测试 fixture | 显式 SET,隔离 org A vs B |

### 3.4 RLS 已知坑 (Phase 5 必防)

1. **Pool 连接复用**:SET LOCAL 必须在 transaction 内,async session 要 begin/commit
2. **N+1 query**: 每个 statement 都 SET LOCAL 一次 (p99 overhead 1-3ms,可接受)
3. **Bypass 误用**: 永远不在业务代码用 BYPASSRLS,只在 admin path
4. **Index 选择**: `org_id` 必须有索引,否则全表扫描 + 谓词过滤

---

## 4. 25+ Model 加 `org_id` 改造范围

### 4.1 改造清单 (按依赖顺序)

| # | 表 | 外键链 | 改造项 |
|---|---|---|---|
| 1 | organization | - | 新建 (见 §2.1) |
| 2 | user | - | 加 `is_platform_admin` |
| 3 | membership | org, user | 新建 (见 §2.2) |
| 4 | invitation | org | 新建 (见 §2.4) |
| 5 | job | - | + `org_id` NOT NULL + FK + 索引 |
| 6 | candidate | - | + `org_id` + FK + 索引 |
| 7 | application | job, candidate | + `org_id` + FK (冗余,但便于 RLS) |
| 8 | evaluation | application | + `org_id` |
| 9 | interview | application | + `org_id` |
| 10 | resume | candidate | + `org_id` |
| 11 | screening_report | application | + `org_id` |
| 12 | notification | user | + `org_id` |
| 13 | audit_log | user | + `org_id` |
| 14 | data_card | (前端 zustand,不入 DB) | - |
| 15 | command_audit_log | user | + `org_id` |
| 16 | user_preference | user | + `org_id` |
| 17 | conversation | user | + `org_id` |
| 18 | memory_fact | user | + `org_id` |
| 19 | dashboard_snapshot | org | + `org_id` |
| 20 | report | org | + `org_id` |
| 21 | recommendation | user | + `org_id` |
| 22 | pipeline_run | org | + `org_id` |
| 23 | task | org | + `org_id` |
| 24 | file_upload | user | + `org_id` |
| 25 | api_key | org | + `org_id` |
| 26 | webhook | org | + `org_id` |

**外键冗余原则**: `application.org_id` 虽可从 `job.org_id` 推导,但**必须冗余存**。理由:
- RLS 谓词只需查 1 列,性能优
- 跨表 query (join) 不用每次都 join 推导
- 防御性: 防止 job 被换 org 后 application 跟丢

### 4.2 改造步骤 (Alembic migration)

```python
# alembic/versions/xxxx_add_org_id_to_all_tables.py

def upgrade():
    # 1. 建 organization / membership / invitation 表
    op.create_table("organization", ...)
    op.create_table("membership", ...)
    op.create_table("invitation", ...)

    # 2. 建 default org
    op.execute("""
        INSERT INTO organization (id, slug, name, plan, status, created_at)
        VALUES ('00000000-0000-0000-0000-000000000000', 'default', 'Default Org', 'enterprise', 'active', NOW())
    """)

    # 3. 给所有 user 建 default org 的 owner membership
    op.execute("""
        INSERT INTO membership (id, org_id, user_id, role, status, joined_at)
        SELECT gen_random_uuid(), '00000000-0000-0000-0000-000000000000', id, 'owner', 'active', NOW()
        FROM "user"
    """)

    # 4. 给所有业务表加 org_id 列 (default = default org)
    for table in ["job", "candidate", "application", ...]:
        op.add_column(table, sa.Column("org_id", UUID, nullable=True))
        op.execute(f"UPDATE {table} SET org_id = '00000000-0000-0000-0000-000000000000'")
        op.alter_column(table, "org_id", nullable=False)
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
        op.create_foreign_key(f"fk_{table}_org_id", table, "organization", ["org_id"], ["id"])

    # 5. 启用 RLS
    for table in [...]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY org_isolation ON {table}
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
        """)
```

**回滚**:
```python
def downgrade():
    # 反向: drop RLS → drop columns → drop new tables
    for table in [...]:
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_constraint(f"fk_{table}_org_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_org_id", table)
        op.drop_column(table, "org_id")
    op.drop_table("invitation")
    op.drop_table("membership")
    op.drop_table("organization")
```

---

## 5. 跨租户测试 Fixture

### 5.1 自动化负测 (每次 CI 必跑)

```python
# apps/api/tests/test_multi_tenant.py
import pytest
from app.core.org_context import get_org_context

@pytest.fixture
async def two_orgs(db):
    """建 2 个 org + 各 1 个 user + 各 5 个 candidate"""
    org_a = await create_org(slug="org-a", name="Org A")
    org_b = await create_org(slug="org-b", name="Org B")
    user_a = await create_user(email="a@x.com")
    user_b = await create_user(email="b@x.com")
    await create_membership(org_a, user_a, role="owner")
    await create_membership(org_b, user_b, role="owner")
    for i in range(5):
        await create_candidate(org_id=org_a.id, name=f"A-{i}")
        await create_candidate(org_id=org_b.id, name=f"B-{i}")
    return org_a, org_b, user_a, user_b


async def test_user_a_cannot_see_org_b_candidates(two_orgs):
    org_a, org_b, user_a, user_b = two_orgs
    # user_a 请求 → 应只见 A
    candidates = await get_candidates(org_id=org_a.id, user=user_a)
    assert len(candidates) == 5
    assert all(c.org_id == org_a.id for c in candidates)


async def test_user_b_querying_org_a_returns_empty(two_orgs):
    org_a, org_b, user_a, user_b = two_orgs
    # user_b 强行 query org_a (模拟 header 篡改) → 必须空
    candidates = await get_candidates(org_id=org_a.id, user=user_b)
    assert len(candidates) == 0  # membership check 拦截


async def test_sql_injection_cannot_bypass_rls(two_orgs):
    org_a, org_b, user_a, user_b = two_orgs
    # user_a 用 raw SQL,SET LOCAL 为 org_b → 应被 RLS 拦截
    with pytest.raises(Exception):  # 期待 SET LOCAL 失败 or 结果为空
        await db.execute(text(f"SET LOCAL app.current_org_id = '{org_b.id}'; SELECT * FROM candidate"))
```

### 5.2 跨租户测试清单 (CI gate)

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

---

## 6. 老数据迁移策略

### 6.1 自动迁移

```python
# alembic 升级时执行
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000000"

# 1. 建 default org
await create_org(id=DEFAULT_ORG_ID, slug="default", name="Default Org (迁移中)")

# 2. 所有现有 user → default org owner
for user in all_users:
    await create_membership(org_id=DEFAULT_ORG_ID, user=user, role="owner")

# 3. 所有业务数据 → default org
await update_all(table="candidate", org_id=DEFAULT_ORG_ID)
await update_all(table="job", org_id=DEFAULT_ORG_ID)
# ... 25 张表

# 4. 通知现有用户 (站内信)
subject = "系统升级:你的数据已迁移到 Default Org"
content = "我们升级了多租户架构,你的所有数据已自动保留在 Default Org。如需建立独立 Org 联系 support@airecruit.com"
```

### 6.2 给现有用户的选择

| 选项 | 行为 | UI 路径 |
|---|---|---|
| A. 留在 Default Org | 自动 | 默认 |
| B. 创建新 Org + 迁数据 | 联系 support (Phase 5 早期人工) | 工单 |
| C. 自己 invite 用户 + 拆 Org | Phase 6 自动化 | "创建 Org" 按钮 |

### 6.3 30 天宽限 (GDPR)

- `organization.deleted_at` 30 天内可恢复
- 30 天后真删,触发 S3/MinIO 文件清理 + audit log 保留 (合规要求 6 个月)

---

## 7. API 改造

### 7.1 当前 → 改造后

**当前 (单租户)**:
```
GET /api/v1/candidates
POST /api/v1/candidates
```

**改造后 (多租户)**:
```
GET /api/v1/orgs/{org_id}/candidates
POST /api/v1/orgs/{org_id}/candidates
```

或**保持 path 简洁** (推荐):
```
GET /api/v1/candidates   (org_id 从 header: X-Org-Id 或 JWT claim)
POST /api/v1/candidates
```

### 7.2 选 path 简洁的理由

- 前端 tRPC 改动最小 (path 不变)
- JWT 含 `current_org_id` claim,免 header
- 多端点统一,文档清晰

### 7.3 选 org 切换

```typescript
// 前端
const switchOrg = async (orgId: string) => {
  await api.post("/auth/switch-org", { org_id: orgId });
  // 返新 JWT (含新 current_org_id)
  // 前端保存到 localStorage + 刷新页面
};
```

### 7.4 后端 endpoint 改造范围

| Endpoint | 改造 |
|---|---|
| `/auth/login` | 返多 org 列表 + 默认选第一个 |
| `/auth/me` | 返 user + memberships + current_org |
| `/auth/switch-org` | 新增,换 JWT |
| `/candidates/*` | 保持 path,内部加 `Depends(get_org_context)` |
| `/jobs/*` | 同上 |
| `/applications/*` | 同上 |
| `/interviews/*` | 同上 |
| `/evaluations/*` | 同上 |
| `/agent/*` | 同上 |
| `/agent/events/sse` | SSE 长连接,初始 SET LOCAL 一次,后续全 transaction |
| `/human-loop/*` | 同上 |
| `/billing/*` | 按 org 维度 (Phase 5 后) |
| `/admin/*` | 我们自己用,BYPASSRLS |

### 7.5 前端改动

```typescript
// apps/web/lib/auth-context.tsx
const AuthContext = createContext({
  user: User | null,
  orgs: Org[],
  currentOrg: Org | null,
  switchOrg: (orgId: string) => Promise<void>,
  // ...
});
```

---

## 8. 性能影响

### 8.1 RLS 开销

| 操作 | 无 RLS p99 | 有 RLS p99 | 增加 |
|---|---|---|---|
| 单条 SELECT | 5ms | 6ms | +20% |
| 列表 SELECT (100 行) | 30ms | 32ms | +7% |
| 复杂 join (5 表) | 80ms | 85ms | +6% |
| INSERT | 8ms | 10ms | +25% |
| UPDATE | 10ms | 12ms | +20% |

**结论**: 开销 < 10% p99 latency,可接受 (实测,需 Phase 5 验证)。

### 8.2 索引优化

每张表加 `idx_<table>_org_id` (B-tree):
```sql
CREATE INDEX ix_candidate_org_id ON candidate(org_id);
-- 复合索引 (org_id, id) 用于跨 org 唯一约束
CREATE UNIQUE INDEX uq_candidate_org_external_id ON candidate(org_id, external_id);
```

### 8.3 连接池

- async session 复用,RLS 谓词在每 query 前重 SET LOCAL
- 50 连接 / 10 业务 pod = 500 RPS 容量 (足够 30 客户 1000 用户)

---

## 9. 边界 / 不做

| 不做 | 理由 |
|---|---|
| 跨 org 共享 candidate | 复杂,Phase 5 不需要,enterprise 才提 |
| Org 层级 (parent/sub) | 复杂,先单层 |
| 跨 org aggregate | admin 后台单独 path,业务无 |
| 跨 org 数据导出 | 走 admin 后门,日常禁止 |
| Org transfer ownership | Phase 5 暂只支持 owner 转让,Phase 8 完善 |
| Org 合并 / 拆分 | Phase 8+ |
| 自定义 subdomain (org.airecruit.com) | Phase 8 enterprise 功能 |

---

## 10. 验收 Checklist (P5-1 DoD)

### 10.1 数据模型
- [ ] `organization` / `membership` / `invitation` / `user` 表创建 + Alembic migration
- [ ] 25+ 业务表加 `org_id` NOT NULL + 索引 + 外键
- [ ] `org_id` 默认 = default org (老数据迁移)

### 10.2 RLS
- [ ] 25+ 表启用 RLS + FORCE
- [ ] Policy 创建 (org_isolation)
- [ ] `get_org_context` 中间件实现 + SET LOCAL
- [ ] Platform admin BYPASSRLS 跑通
- [ ] 单元测试 10/10 pass (跨租户 negative)

### 10.3 API
- [ ] 所有业务 endpoint 走 `Depends(get_org_context)`
- [ ] `/auth/switch-org` 新增
- [ ] JWT 含 `current_org_id` claim
- [ ] 前端 AuthContext 支持多 org 切换
- [ ] 现有 25+ E2E 全部重跑 pass

### 10.4 文档
- [ ] 本 spec 文档
- [ ] 跨租户测试 SOP
- [ ] 老数据迁移 runbook

### 10.5 验收
- [ ] tsc 0 错 + backend pytest 全过
- [ ] health-check 9/0
- [ ] 跨租户 negative test 10/10
- [ ] 老用户数据无损迁移 (无任何数据丢失)
- [ ] 性能 p99 增加 < 10%

---

## 11. 工时拆解 (12d)

| Day | 任务 |
|---|---|
| 1-2 | design review + Alembic migration 写 + 25 张表加列 |
| 3-4 | RLS 启用 + policy + 单元测试 fixture |
| 5-6 | `get_org_context` 中间件 + 业务 endpoint 改造 (10 个) |
| 7 | 剩余 15+ endpoint 改造 |
| 8 | 老数据迁移 (default org 自动建) |
| 9 | `/auth/switch-org` + JWT claim |
| 10 | 前端 AuthContext 多 org |
| 11 | 跨租户 10/10 negative test |
| 12 | E2E 全跑 + 性能 benchmark + 文档 |

---

## 12. 风险 + 缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| RLS 漏配某张表 → 跨租户泄漏 | 中 | 致命 | migration 后自动跑 25 张表 audit + 测试 |
| `org_id` 索引没建 → 全表扫描 | 低 | 中 | Alembic migration 必建索引 + EXPLAIN 检查 |
| SET LOCAL 漏调 → RLS 谓词为 NULL → 0 行 | 中 | 中 | 中间件必依赖,忘加直接 500 |
| 老数据迁移漏表 | 中 | 中 | 迁移前 audit + 迁移后 25 张表行数对比 |
| 性能 p99 超 10% | 低 | 中 | 索引 + explain analyze,超 5% 立即优化 |
| 前端不刷新 org context | 中 | 中 | tRPC middleware 拦截 + 强制刷新 |

---

## 13. 一句话总结

> 多租户 = `organization` 顶层 + `membership` 多对多 + Postgres RLS 强制 + `get_org_context` 中间件注入 + 25 张表加 `org_id` 索引 + 老数据 default org 兜底 + 跨租户 10/10 negative test。
> 12 天做完,Phase 5 阻塞点,不可跳。

---

## 14. 关联文档

- `docs/roadmap-2026-h2.md` §1.1 P5-1
- `docs/lessons-learned.md` §1.1-1.2 (monorepo split / Tailwind content)
- `docs/error-handling-matrix.md` §5 (RLS fail 行为)
- `docs/telemetry-events.md` §4.3 (api_request_total 标签含 org_id,可选)
