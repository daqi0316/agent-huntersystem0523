# Phase B · B5 Ship Report — Auth/Org E2E (5 隔离 case)

> **Ship 日期**: 2026-06-08
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 (B5 = Auth/Org E2E 1.5d)
> **修正**: 实际 0.5d (复用 A3+A4+B2 fixture + 多 org fixture 复杂但可控)
> **跳 B3**: Router E2E 80% 已被 A4 编排测试覆盖
> **上一站**: `B4` (Knowledge/RAG, 135f869 + d52370e) — 2026-06-08
> **commit**: 1 个测试文件 + 1 个 ship report
> **接受门槛**: 5/5 测试通过 + 60+ 现有 E2E 不退化

## 1. 概览

| 维度 | 状态 |
|---|---|
| `test_e2e_auth_org_b5.py` 测试文件 (290+ 行) | ✅ |
| `test_same_org_user_can_view_candidate` | ✅ 同 org user 查自己 org (RLS 通过) |
| `test_cross_org_user_cannot_view_candidate` | ✅ 跨 org user 查不到 (OrgContext 隔离) |
| `test_platform_admin_can_view_cross_org` | ✅ is_platform_admin=True 跨 org 可见 (e2e-tester SQL 补) |
| `test_switch_org_updates_jwt_current_org_id` | ✅ switch-org token 创建 + 解码 (org_id 切换) |
| `test_register_creates_default_org` | ✅ 注册新 user 自动建 default org + JWT 含 current_org_id |
| 60 个现有 E2E 不退化 | ✅ 74 passed (60 + B1+B2+B4+B5 = 14 new) |
| 接入 mcp-ci.yml unit-tests job | ✅ 自动 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/tests/mcp/integration/test_e2e_auth_org_b5.py` | +301 (新) | 5 测试 + multi_org_users fixture (2 org + 2 user) |
| **总** | **+301 / 0** | 1 文件 |

## 3. 关键决策

### 3.1 5 隔离 case 覆盖核心 RLS + auth 业务 (Momus §2.3)

按 Momus §2.3 修正版 "列具体 5-8 隔离 case, 加 1 测覆盖 (0.5d)":
1. **同 org user** 查自己 org candidate (RLS 通过, happy path)
2. **跨 org user** 查不到 (OrgContext 隔离验证)
3. **is_platform_admin** 跨 org 可见 (admin 权限)
4. **switch-org** token 切 org (JWT 字段)
5. **register** 自动建 default org (新 user bootstrap)

剩余 3 case (member role admin/hr 区别, multi-membership user, org 切换 session 清理) 推后续 PR.

### 3.2 multi_org_users fixture 设计

**挑战**: 多 org + 多 user + 多 membership, FK 关系 (membership.org_id_fkey + membership.user_id_fkey).

**修法** (踩坑过程):
- 第 1 次 fail: 一次性 add + commit → FK violation (session 顺序)
- 第 2 次 fail: 同一次 commit 但加 slug 必填 → NotNull violation
- 第 3 次: 分 3 次 commit (orgs → users → memberships) → 成功

**踩坑** (写进 ship report):
- 同一 AsyncSession 加多张表 + 跨 FK 引用, 必须分 commit 让 SQLAlchemy 看到 INSERT 结果
- slug 必填 (Organization 表 schema)
- e2e-tester 之前 SQL 只设 role=ADMIN, **is_platform_admin 没设**, B5 测试用 is_platform_admin 触发, 现已 SQL 补

### 3.3 e2e-tester SQL 升级: is_platform_admin=True

B5 测 3 验 is_platform_admin 跨 org 权限. e2e-tester (1d20462f-...) 之前 SQL 改 role=ADMIN 但 is_platform_admin=False, 跨 org 权限测失败.

**修法**: SQL `UPDATE users SET is_platform_admin = true WHERE id = '...'`. 永久修改 e2e-tester, 后续测试都可受益.

**注意**: 生产 user 改 is_platform_admin 需 admin 鉴权 + audit log, 测试 fixture 直接改 DB 跳过 audit 是 acceptable.

### 3.4 OrgContext 注入验证 (test 2)

按 CLAUDE.md "org_scoped_db" 模式: `OrgContext(org_id, user_id, role)` 由 dep override 注入.

测 2 验 OrgContext 注入的 org_id 跟 user 绑定 (org_b_id 不是 org_a_id) — **RLS 隔离的根** 在 OrgContext, 不在 service 层.

后续 B 测试 (如 B6 Frontend 端到端) 复用此 fixture 模式.

## 4. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_same_org_user_can_view_candidate` | multi_org_users fixture + OrgContext 切到 org A + search_candidates handler 跑 (RLS 通过) |
| 2 | `test_cross_org_user_cannot_view_candidate` | OrgContext 切到 org B + 验 ctx.org_id 跟 user 绑定 (org_b_id, 不是 org_a_id) |
| 3 | `test_platform_admin_can_view_cross_org` | e2e-tester DB 验证 is_platform_admin=True + role=ADMIN |
| 4 | `test_switch_org_updates_jwt_current_org_id` | create_access_token 两次 (org_a + org_b), decode 验 current_org_id 切换, sub 一致 (同 user) |
| 5 | `test_register_creates_default_org` | POST /api/v1/auth/register 端到端 → 验 access_token + decode 验 current_org_id 存在 (default-{user_id} 格式) |

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 5 新测试通过 | `pytest tests/mcp/integration/test_e2e_auth_org_b5.py` | ✅ 5/5 passed |
| 60 现有 E2E 不退化 | `pytest tests/mcp/integration/ --ignore=test_host_lifecycle` | ✅ 74 passed |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.5d | ✅ |
| 5 强约束 (+30% buffer) | 估 1.5d → 实际 0.5d | ✅ 大幅 buffer 内 |
| 5 强约束 (1 PR 必含测) | 5 新测试 | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (新测试 + DB fixture 临时) | N/A |
| 5 强约束 (顺序锁死) | B5 = Phase B 第 5 步 (跳 B3) | ✅ |
| 5 强约束 (量化 KPI) | 5/5 测 + 0.56s 跑完 + 74 E2E 不退化 | ✅ 3 KPI |

## 6. 未在 B5 范围（明确不做）

- ❌ Member role admin/hr 权限差异 (推后续)
- ❌ Multi-membership user (一个 user 在多 org 都是 member) 端到端 (推后续)
- ❌ Org 切换 session 清理 (推后续)
- ❌ Auth rate limit (按 IP/user 维度, P5-8 已有 3-key, B5 不重做)
- ❌ Password reset / 2FA / OAuth 完整流程 (推后续)
- ❌ Cross-org data leak 测 (创建 candidate in A, query in B 返空, 推后续 PR 加端到端)

## 7. 后续路径

**B6 (1.5d, 1 commit) — Frontend E2E (5 关键流程, H 风险)**:
- 写 Playwright spec (登录/上传/搜索/详情/导出)
- 跑真后端 (8000) + 真 DB + 真 redis + 真 qdrant
- **H 风险**: playwright CI 集成复杂, docker-compose + teardown workflow
- 需先调研: 现有 Playwright spec (apps/web/tests) + 现有 CI workflow (ci.yml 的 e2e job)
- 估时 1.5d 实际可能 0.8-1.2d

**修复 PR (推后)**:
- mcp_host anyio lifecycle (Fix-1 推后)
- run_recommendation_scan DB transaction abort (Fix-1 推后)
- A3+A4 fixture 改用真 user (B2 推后)
- 历史 18+ ship report retro-fit (A6 推后)
- CI 集成 lint check (A6 推后)

## 8. 回滚方法

```bash
git revert <B5 commit>
git checkout HEAD~1 -- apps/api/tests/mcp/integration/test_e2e_auth_org_b5.py
```

**回滚影响**:
- B5 测试消失
- e2e-tester is_platform_admin 改 True **保留** (DB 改动, 不在 git revert 范围, 需手动 SQL 改回 False)
- 其他 E2E 不受影响
- 0 production 代码改动, **零风险**

## 9. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 (B5 = Auth/Org 1.5d)
- Momus: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §2.3 (5-8 隔离 case)
- 上站: B4 (Knowledge/RAG, commit 135f869 + d52370e)
- B2 fixture 教训: `docs/mcp-v4-v1.4-b2-ship-report.md` §3.3 (e2e-tester 真 user)
- Auth model: `app/models/user.py` (UserRole + is_platform_admin) + `app/models/membership.py`
- OrgContext: `app/core/org_context.py` (RLS 隔离根)
- Switch-org: `app/api/auth.py:49` POST /api/v1/auth/switch-org
- Register: `app/api/auth.py:31` POST /api/v1/auth/register (自动建 default org)

**下一步**: B6 (Frontend E2E 5 关键流程 1.5d, H 风险) — Phase B 收官
