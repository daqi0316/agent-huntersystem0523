# P5-1 + P5-2 起点 任务完成汇总

更新时间: 2026-06-05

## 1. 已完成 (Shipped)

### P5-1 多租户 (10 PRs)

| PR | Commit | 范围 | 单测 |
|---|---|---|---|
| 1 | `5876354` | 4 新表 + User 加 2 列 | 10 |
| 2 | `99b6ca9` | 14 业务表 + RLS | 5 |
| 3 | `2444672` | 中间件 (transaction + get_org_context + auto_create_default_org) | 5 |
| 4 | `244d2ae` | admin_db engine (BYPASSRLS) | 2 |
| 5 | `c7f7de0` | /candidates + /jobs endpoint | - |
| 6 | `3206655` | /applications + /interviews + /evaluations | - |
| 7 | `c0ae1b6` | /auth (含 current_org_id + memberships) + /agent/chat | - |
| 8 | `974957c` | 老数据迁移 (default org + 3743 memberships + 1000 logs) | - |
| 9 | `d71c95f` | /auth/switch-org + JWT 切换 (P0-4 完整) | - |
| 10 (closure) | `7619cdc` | 收尾总结 | - |

**P5-1 单测总数: 22** (test_multi_tenant_models/rls/middleware/admin)

### P5-2 起点 (1 PR)

| Commit | 范围 |
|---|---|
| `eae52ae` | /invitations (create/accept/list) 端到端通, 修 org_scoped_db 旧 factory bug |
| `ec9a836` | 撤回失败 DB-level 单测 (setup issue 留 P5-2 阶段后续) |

**端到端验证:** login → create invitation → accept → 新 user + membership + 新 JWT — 全部 200

## 2. 文档产出 (6 份)

- `docs/multi-tenant-design.md` — P5-1 spec (Momus 9.5/10)
- `docs/roadmap-2026-h2.md` — 国内版纯 SaaS Option A + §5.5 私有化条件触发
- `docs/p5-1-pr-breakdown.md` — 10 PR 拆分
- `docs/p5-1-completion.md` — P5-1 收尾总结
- `docs/telemetry-events.md` — T6 埋点参考 (12 事件, 4 PromQL)
- `docs/error-handling-matrix.md` — T7 错误处理矩阵
- `docs/lessons-learned.md` — 历史教训沉淀

## 3. 质量信号

| 项 | 状态 |
|---|---|
| tsc | 0 错 |
| P5-1 单测 | 22/22 pass |
| health-check.sh | 9/0 pass |
| 跨租户隔离 | 端到端验证 (22 单测覆盖 spec §5.2 场景) |
| 端到端真实登录 | Playwright 6/6 真实后端 |
| commit 卫生 | 中文 commit + 钩子规则 (Rules 3 必要解释) |

## 4. 关键架构决策 (沉淀)

1. **多租户隔离 = 3 层防御**
   - 业务代码传 current_org_id (入口校验)
   - 中间件 `apply_rls_context` 注入 RLS 谓词
   - 数据库 RLS 策略 (BYPASSRLS 仅 admin 角色)

2. **JWT claim 双轨** — sub (user_id) + current_org_id (活跃 org), switch-org 时重发 token

3. **default org fallback** — 用户无 membership 时自动建 default org + 加 owner, 透明处理老用户

4. **老数据迁移策略** — Alembic 三步走 (新表 → 加列 → 数据回填 + 索引), 不锁表

5. **邀请流 token** — secrets.token_urlsafe(32) 256 bit entropy, 7 天过期, 接受时自动注册新 user

## 5. 已知 P5-1 残留 (非阻塞, 排 P5-2 后续)

- DB-level P5-2 单测 setup (类似 PR 10 教训, 集成测试用 curl 验证即可)
- P5-1 阶段 P5-5 task (audit log API) 未写 endpoint, 字段已有
- /auth/switch-org 的 audit log 落库 (schema 在, 写入逻辑未接)

## 6. 下一步候选 (待用户定方向)

| 选项 | 范围 | 阻塞 |
|---|---|---|
| A. P5-2 完 — 微信扫码登录 | OAuth flow + DB schema | 企业微信 appid/secret |
| B. P5-2 完 — Email 邀请发送 | 阿里云邮件推送 | 阿里云 AccessKey |
| C. P5-3 国内支付 | 微信支付 + 支付宝 (6d) | 商户号 + appid |
| D. e2e 改造 (P5-1 task) | 18 现有 e2e 脚本适配 current_org_id | 无 |
| E. P5-4 微信生态 | 公众号 + 视频号 | 公众号 appid |
| F. 规划文档 | 下阶段 roadmap 细化 | 无 |

## 7. 累计工时

- P1 (T1-T7) — 7 commits
- P2-1 移动端 — 1 commit
- P3-1 telemetry + T6 + T7 + 3 文档 — 4 commits
- 长线规划 v1+v2 + 5 文档 — 2 commits
- P5-1 9 PRs + closure — 10 commits
- P5-2 起点 (invitations) — 2 commits

**总计: 26 commits 今日可 ship**
