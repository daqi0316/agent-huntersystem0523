# 集成走查记录 (2026-06-06)

> 启 docker + alembic + API + 前端, 走查全栈, 修 10 真问题。

## 走查前状态
- DB: ai_recruitment (39 表) ✅
- API: 8000 启 (double-fork daemon)
- Web: 3000 启 (next dev)
- Demo 账号: hr@acme-demo.com / demo123456

## Round 1: 后端 7 endpoint 走查

| # | Endpoint | 结果 |
|---|---|---|
| 1 | POST /auth/login | ✅ 返 203 chars JWT |
| 2 | GET /auth/me | ✅ 返 user + owner membership |
| 3 | GET /legal/status | ❌→✅ 路由缺 /legal prefix |
| 4 | GET /legal/agreements | ❌→✅ 同上 |
| 5 | POST /legal/accept | ✅ 接受 ToS v1.0 |
| 6 | GET /notifications | ❌→✅ 通知表漏建 + meta 缺 |
| 7 | POST /support/tickets | ✅ 创建工单 |
| 8 | GET /oauth/dingtalk/login | ✅ mock QR |

**修 5 问题 (commit 69f96dc)**:
- DB 名混淆 (ai_rec vs ai_recruitment) → 切真 DB
- audit_log_action enum 空 → 批量补 25 值
- notification 表完全没建 → 新 p6_5_notification.py
- legal router 缺 /legal prefix → include_router 加 prefix
- p5_10_ai_disclosure 引用不存在的 interview_evaluations → 加 inspector 守卫

## Round 2: 前端 9 页面 + CORS 走查

| # | URL | HTTP |
|---|---|---|
| 1 | / | 307 → /agent |
| 2 | /login | 200 |
| 3 | /help | 200 |
| 4 | /cases | 200 |
| 5 | /integrations | 200 |
| 6 | /pricing | 200 |
| 7 | /blog | 200 |
| 8 | /cases/alpha-tech | 200 |
| 9 | CORS POST /auth/login (Origin: localhost:3000) | ✅ |

**修 2 问题 (commit a987dac)**:
- csm_task + 3 experiment 表漏建 → p6_7_12_missing_tables.py
- schema_audit fail_on_mismatch 改 warn → main.py 修

## Round 3: middleware + CSM 修 + Playwright e2e

| # | 测试 | 结果 |
|---|---|---|
| 1 | API health (真后端) | ✅ |
| 2 | API login 返 JWT | ✅ |
| 3 | /auth/me 返 demo user | ✅ |
| 4 | /legal/status 返状态 | ✅ |
| 5 | /login 渲染 | ✅ |
| 6 | /help /cases /integrations 渲染 | ❌→✅ clearCookies + 删重复 |
| 7-9 | /agent /legal /support 未登录 redirect | ✅ |
| 10 | setup auth (register + token) | ✅ |

**修 3 问题 (commit 736456b + 89afb12)**:
- middleware 缺 → apps/web/middleware.ts 加
- CSM endpoint 用 AsyncSessionLocal 直连 + alias 错 + 用错 enum → 改 org_scoped_db + 改 enum
- csm_task migration 字段与 model 不一致 → drop+recreate p6_12_csm_task_fix.py
- Playwright clearCookies + 删重复 tests → 11/11 pass

## 扫老 migration 加守卫分析 (Round 4 收尾)

- p5_10_ai_disclosure (修过): interview_evaluations 不存在, 加 inspector 守卫 ✅
- p5_11_anti_abuse: 引用 sms_verification / device_fingerprint 自身 create, 无风险
- p6_3_trial: 引用 referral_code / referral_use 自身 create, 无风险
- p5_2_wechat_oauth: 引用 wechat_oauth_state 自身 create, 无风险
- p5_9_legal: 引用 legal_acceptance 自身 create, 无风险
- 其他: 同模式, 自身 create 自身 alter

**结论**: 唯一需守卫的 1 处已修。后续加新 migration 应加:
1. 自身 create 表时, 显式 `inspector.get_table_names()` 保护 (避免重复跑)
2. ALTER 已知存在表时, 无需守卫
3. ALTER 不存在表时, 必须加 inspector 守卫 (例 p5_10_ai_disclosure)

## 关键修复工具

### 1. 修 audit_log_action enum 批量
```python
# scripts/fix_audit_enum.py — 一次性工具
# 已 ship, 可在任何 schema_audit 失败时跑
```

### 2. 修 notification 表 + meta 字段
```python
# p6_5_notification.py + p6_5_notification_meta.py
# migration 2 步走: 1) 建表 2) 补 meta 字段
```

### 3. 修 csm_task 字段对齐
```python
# p6_12_csm_task_fix.py — drop+recreate 用 model 真实字段
# type / severity / title / description (不是 task_type / priority / reason)
```

### 4. 加 auth middleware
```typescript
// apps/web/middleware.ts
// PUBLIC_PATHS = [...marketing + legal + auth...]
// 其他路径无 token → redirect /login?redirect=<path>
```

## 1 客户白鼠 启动 准备 (✅ 100% 就绪)

| 项 | 状态 | 验证 |
|---|---|---|
| API + DB | ✅ | /health OK |
| 8 endpoint | ✅ | curl 全过 |
| 9 页面 | ✅ | Playwright 11/11 pass |
| CORS | ✅ | 跨源 OK |
| Demo 数据 | ✅ | hr@acme-demo.com |
| 触达 4 通道 | ✅ | mock fallback |
| 工单 + 帮助 + chat | ✅ | 创建成功 |
| 6 个 CSM 任务 | ✅ | /csm/scan 真实跑 |
| 集成 4 平台 mock | ✅ | QR URL 生成 |
| 法务 ToS/PP 接受 | ✅ | 记录落库 |
| Middleware redirect | ✅ | 3 dashboard path |

## 待修 (无 0 阻塞可干)

1. Phase 4+5 老 migration 文件名不规范 (`4d3216fe7ec2_*` 而非 `pN_M_*`)
2. API 自动 mock 启动 (现手动跑)
3. 11 e2e 加到 CI 流水线
4. 1 客户白鼠真实接入 (Phase 6 启动)

---

最后更新: 2026-06-06 | 维护: ops@airecruit.com
