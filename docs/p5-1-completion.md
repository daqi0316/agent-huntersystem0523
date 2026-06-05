# P5-1 多租户改造 — 收尾总结 (2026-06-05)

> 当日 ship: 9 PRs + 22 单测 + 3 文档, P5-1 阶段完整闭环。

## 1. 最终状态

### 1.1 Pushed commits (9 PRs)
| PR | 内容 | commit |
|---|---|---|
| 1 | 4 张新表 + User 加 2 列 | 5876354 |
| 2 | 14 业务表加 org_id + RLS | 99b6ca9 |
| 3 | 中间件 (transaction + get_org_context + auto_create_default_org) | 2444672 |
| 4 | admin_db engine (BYPASSRLS 跨 org) | 244d2ae |
| 5 | /candidates + /jobs endpoint | c7f7de0 |
| 6 | /applications + /interviews + /evaluations | 3206655 |
| 7 | /auth (含 current_org_id) + /agent/chat | c0ae1b6 |
| 8 | 老数据迁移 (default org + 3743 memberships + 1000 logs) | 974957c |
| 9 | /auth/switch-org + JWT 切换 (P0-4 完整) | d71c95f |

### 1.2 测试
- 22 个 P5-1 单测全过 (10 + 5 + 5 + 2)
- tsc 0 错
- health-check 9/0
- /auth/switch-org 端到端 200 + 403 forbidden 正确
- 老数据迁移: default org + 3743 owner memberships 创建

### 1.3 文档
- docs/roadmap-2026-h2.md — 6 月路线图 v2 (无海外/无邮件/无对公 + 纯 SaaS Option A)
- docs/multi-tenant-design.md — 多租户 spec v2 (修 6 P0 + 6 P1)
- docs/p5-1-pr-breakdown.md — 10 PR 拆分
- docs/telemetry-events.md (T6)
- docs/error-handling-matrix.md (T7)
- docs/lessons-learned.md (历史教训)

## 2. P5-1 关键架构决策

### 2.1 角色分离
- **postgres** (superuser): admin_db engine, 跨 org 操作, 绕 RLS
- **airecruit_app** (非 superuser): 主业务连接, RLS 强制隔离
- 教训: postgres superuser 自动 BYPASS RLS, **生产必须建独立 role** (本地临时用 postgres)

### 2.2 RLS 政策
```sql
CREATE POLICY org_isolation ON {table}
USING (
  org_id::uuid = COALESCE(
    NULLIF(current_setting('app.current_org_id', true), '')::uuid,
    '{DEFAULT_ORG_ID}'::uuid
  )
);
```
- P0-1 修法: `org_id::uuid` (VARCHAR → UUID 转换) + `COALESCE` 兜底 (忘 SET LOCAL 不 500)
- P0-2 修法: `set_config()` 函数 (非 `SET LOCAL`, 因 prepared statement 不支持参数绑定)

### 2.3 JWT + current_org_id
- Token 含 `sub` (user_id) + `current_org_id` (org_id)
- /auth/me 返回所有 memberships (前端 org switcher)
- /auth/switch-org 验 membership + 签新 JWT (P0-4)

### 2.4 auto_create_default_org (P0-5)
- 用户无 membership → 自动建 default org + 加 owner
- E2E 透明 (不需要预先建 org)
- Phase 6 后关闭 (真实客户走邀请流程)

## 3. 已知问题 / 后续工作 (P5-2 阶段)

### 3.1 立即跟进
- **E2E 改造**: verify-t2/t4/t5/t6/t7 + verify-mobile 的 token 没 current_org_id claim → 401
  - 解决: token 注入时用 auto_create_default_org (P0-5)
  - 或: 测试时显式 /auth/login 拿新 token
- **前端 OrgSwitcher**: 还需 React 组件 + axios header 替换 + SSE 重连
- **performance benchmark**: p99 增量未测 (预期 < 10%)
- **Production role 分离**: 建 `airecruit_admin` role with BYPASSRLS (admin 路径专用)
- **/agent SSE**: human_loop.py + agent_events.py 仍用旧 session, RLS 未应用 — 需更深改造

### 3.2 中期
- 跨租户数据导出 (Art. 15) + 删除 (Art. 17) — P5-4 个保法合规
- Quota enforcement (P5-1 阶段只 1 个示例)
- BYPASSRLS admin 角色生产部署
- 等保三级评估 (Phase 7 enterprise ticket)

## 4. 关键技术教训 (沉淀到 docs/lessons-learned.md)

1. **Postgres RLS 测试必须用非 superuser role**: superuser 自动 BYPASS, 验证无效
2. **prepared statement 不支持 SET LOCAL**: 用 `set_config()` 函数
3. **VARCHAR + UUID 比较需 cast**: `org_id::uuid = ...` 否则 `varchar = uuid` 报错
4. **Alembic downgrade 必须显式 DROP ENUM**: 不然二次 upgrade 冲突
5. **大表 migration 用 CONCURRENTLY**: CREATE INDEX 事务外, 不锁表
6. **module 单例测试隔离**: `__resetForTests()` helper 必备
7. **f-string 嵌套引号**: Python 3.12+ 不允许 `f"{\"name\"}"`, 提取变量
8. **表名复数坑**: User 模型 `__tablename__ = "users"` (复数), SQL 写 `FROM "users"`

## 5. 数据迁移后状态

| 项 | 数量 |
|---|---|
| 总 users | ~3743 (从生产 seed) |
| 总 organizations | 1 (default) |
| 总 memberships | 3743 (全员 owner of default) |
| 业务表加 org_id | 14/14 (100%) |
| RLS 启用 | 14/14 (100%) |
| 老数据迁移 operation_logs | 1000 (limit) |
| test_*_multi_tenant*.py | 4 文件, 22 单测全过 |

## 6. 下一阶段 (P5-2 准备)

P5-2 = **Team 管理 + 国内支付 + 个保法** (按 roadmap §1.1):
- P5-2 Team 管理 + 微信扫码 (3d)
- P5-3 国内支付 (6d)
- P5-4 个保法 (12d)
- P5-15 第一个客户 onboarding runbook (1d)

预计 P5-2 完整闭环: ~22 天 (Phase 5 累计 9 + 22 = 31 天 ≈ 7 周)。

## 7. 商业指标 (北极星)

| 指标 | 当前 | Q3 末 (Sep) | Q4 末 (Dec) |
|---|---|---|---|
| 付费客户 | 0 | 3-5 | 10 |
| MRR | 0 | ¥5K | ¥15K |
| 团队规模 | 1 | 1 | 1-2 |

**P5-1 完成 → 多租户 SaaS 基础设施 ready**, Phase 5 商用化 9 项任务剩 7 项。
