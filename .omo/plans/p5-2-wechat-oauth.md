# P5-2-A 微信扫码登录 实施规划

**创建时间**: 2026-06-06 01:53
**优先级**: A (推荐, 路线图 P5-2 关键 1/3 任务)
**工时估算**: 1-2 天 (有完整 P5-1 + invitations 模式可复用)
**阻塞依赖**: 企业微信 appid/secret (用户可暂缓提供 — 走 mock mode 本地可验)

---

## 0. 上下文 (已完成的 P5 基础)

| 已 ship | 复用价值 |
|---|---|
| P5-1 多租户 (Organization/Membership/RLS) | 新用户自动建 default org + owner 角色 |
| P5-1 JWT 切换 (sub + current_org_id) | OAuth 回调成功后签同样的 token |
| P5-1 审计日志 (audit_log 表 + log_audit) | 微信登录落 audit (谁/何时/IP) |
| P5-2 起点 /invitations 端到端通 | token 接受 + 注册 + membership 模式 |
| lessons-learned 5 教训 | pre-commit 防 enum bug, set_config 绕 RLS |

---

## 1. 目标

**B2B 客户可"用企业微信扫码"登录本系统** — 这是国内 SaaS 的标配 (替代 email 注册)。

OAuth 流程:
```
[前端 /login] → 调 /api/v1/auth/wechat/qrcode
                ↓
            返 { qrcode_url, state, expires_in }
                ↓
[前端] 渲染二维码 (state 内嵌,用户扫码)
                ↓
[用户] 在企业微信 App 扫码 → 浏览器重定向到 /api/v1/auth/wechat/callback?code=xxx&state=yyy
                ↓
[后端 callback] 用 code 换 access_token + unionid/openid
                ↓ 复用
            查 user (by unionid); 无则自动注册 + 建 default org + owner membership
                ↓
            签 JWT (sub=uid, current_org_id=org)
                ↓
[重定向] 回 /login?token=xxx&org_id=yyy
                ↓
[前端] 存 token → /auth/me 拉 user → 进 dashboard
```

---

## 2. 任务分解 (8 个原子子任务)

### A1. DB schema: User 表加 WeChat 字段 + wechat_oauth_state 表
- **文件**: `apps/api/alembic/versions/p5_2_wechat_oauth.py` (新 migration)
- **修改**: 
  - `users` 表加列: `wechat_unionid VARCHAR(64) UNIQUE`, `wechat_openid VARCHAR(64)`, `wechat_nickname VARCHAR(64)`, `wechat_avatar_url TEXT`, `auth_source VARCHAR(16) DEFAULT 'email'`
  - 新表 `wechat_oauth_state`: `state` (PK), `created_at`, `expires_at`, `used_at`, `redirect_uri`
  - 索引: `idx_users_wechat_unionid` (UNIQUE 部分 NULL)
- **验证**: `alembic upgrade head` 无错;`\d users` 见新列;`\d wechat_oauth_state` 见表

### A2. Config: 加 WeChat OAuth 配置 + mock mode
- **文件**: `apps/api/app/core/config.py` (扩展)
- **新增**:
  - `wechat_corp_id: str = ""` (企业微信 corpID)
  - `wechat_corp_agent_id: str = ""` (自建应用 agentid)
  - `wechat_corp_secret: str = ""` (应用 secret)
  - `wechat_oauth_redirect_uri: str = "http://localhost:3000/api/auth/wechat/callback"`
  - `wechat_qrcode_expire_seconds: int = 600` (10 min)
  - `wechat_mock_mode: bool = True` (默认 mock, 真凭据后再 False)
- **.env.example**: 加 5 个 WECHAT_* 行
- **验证**: `from app.core.config import settings; print(settings.wechat_mock_mode)` 返 True

### A3. Service: 微信 OAuth service (mock + real 双模式)
- **文件**: `apps/api/app/services/wechat_oauth.py` (新)
- **接口**:
  - `async def generate_qrcode(redirect_uri: str) -> dict` — 返 `{qrcode_url, state, expires_in}`, 写 state 入 DB
  - `async def exchange_code(code: str, state: str) -> dict` — 验 state (未用过+未过期) → 调企微 API 换 user_info
  - `async def find_or_create_user(unionid, openid, nickname, avatar) -> User` — 查 → 无则建 + 走 default_org + owner
  - mock 模式: code 返固定 unionid `mock_unionid_001`, 不发真 HTTP 请求
- **验证**: pytest 单元测试 mock 模式跑通

### A4. API: 3 个 endpoint
- **文件**: `apps/api/app/api/auth.py` (扩展, 不新建文件以保持一致)
- **端点**:
  - `GET /auth/wechat/qrcode?redirect_uri=...` → `{qrcode_url, state, expires_in, mock: bool}`
  - `GET /auth/wechat/callback?code=...&state=...` → 302 重定向到前端 `?token=xxx&org_id=yyy&source=wechat`
  - `POST /auth/wechat/mock-login` (仅 mock 模式可用) → 直接返 token, 方便本地开发
- **验证**: curl 走通 mock 模式三步;真模式需真凭据

### A5. Tests: 单元 + 集成
- **文件**: `apps/api/tests/test_wechat_oauth.py` (新)
- **用例** (≥ 6 个):
  1. mock_qrcode_generation 返 state + 写 DB
  2. mock_qrcode_state 已用过 → 401
  3. mock_qrcode_state 已过期 → 401
  4. mock_exchange_code 返 user_info
  5. mock_find_or_create_user 新 unionid → 建 user + default org
  6. mock_find_or_create_user 已存在 unionid → 返老 user
  7. mock_login_e2e 返 JWT
- **验证**: `pytest tests/test_wechat_oauth.py -v` 全过

### A6. Frontend: 登录页加微信扫码按钮
- **文件**: `apps/web/src/app/login/page.tsx` (扩展)
- **UI**:
  - 主"邮箱登录"表单保留
  - 下方分隔线 + "其他登录方式"
  - "企业微信扫码" 按钮 (图标 + 文字)
  - 点击 → 调 `/auth/wechat/qrcode` → 弹 modal 显示二维码
  - 轮询 `/auth/wechat/poll?state=xxx` 查 state 是否被使用 (用户扫码后)
  - 扫到 → 跳 `?token=` 处理页 → 存 token + 跳 dashboard
- **验证**: 浏览器跑通 mock 模式

### A7. Audit log: 微信登录落库
- **修改**: `apps/api/app/api/auth.py` callback 函数
- **内容**: 调 `log_audit(..., action=AuditLogAction.WECHAT_LOGIN, metadata={"unionid": "...", "mock": bool})`
- **新增**: `apps/api/app/models/audit_log.py` `AuditLogAction` 枚举加 `WECHAT_LOGIN = "wechat_login"`
- **验证**: 微信登录后 `SELECT * FROM audit_log WHERE action='wechat_login'` 见新行

### A8. 系统健康检查 + 6/6 验证
- **脚本**: `bash scripts/health-check.sh` (现有 6 步)
- **额外**: 新增第 7 步"微信登录 mock 跑通"
- **验证**: 6/6 pass + 1/1 mock 微信登录

---

## 3. 文件清单 (预计)

| 类别 | 路径 | 类型 |
|---|---|---|
| Migration | `apps/api/alembic/versions/p5_2_wechat_oauth.py` | 新 |
| Service | `apps/api/app/services/wechat_oauth.py` | 新 |
| API 扩展 | `apps/api/app/api/auth.py` | 改 |
| Model 扩展 | `apps/api/app/models/user.py` | 改 |
| Model 扩展 | `apps/api/app/models/audit_log.py` | 改 |
| Config | `apps/api/app/core/config.py` | 改 |
| Tests | `apps/api/tests/test_wechat_oauth.py` | 新 |
| Frontend | `apps/web/src/app/login/page.tsx` | 改 |
| Frontend 组件 | `apps/web/src/components/auth/wechat-qrcode-modal.tsx` | 新 |
| .env.example | `apps/api/.env.example` | 改 |
| Docs | `docs/wechat-oauth-design.md` | 新 |

---

## 4. 验收标准 (Definition of Done)

- [ ] A1: alembic upgrade 成功, users 表新列可见, wechat_oauth_state 表存在
- [ ] A2: settings.wechat_mock_mode 默认 True
- [ ] A3: wechat_oauth service 3 个方法可调
- [ ] A4: 3 个 endpoint 在 mock 模式走通
- [ ] A5: pytest 6+ 用例全过
- [ ] A6: 前端登录页可见微信扫码按钮 + 弹 modal
- [ ] A7: audit_log 落 wechat_login 行
- [ ] A8: bash scripts/health-check.sh 7/7 pass (含新加的 mock 微信登录)

---

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 企微 appid/secret 不到位阻塞真模式 | 默认 mock mode True,真凭据后切 False;staging 才需真凭据 |
| state CSRF 重放 | DB 存 state + used_at NULL 唯一,callback 时 mark used |
| 已有 email 用户首次用微信登录 | 按 unionid 查;email 留空 (`auth_source='wechat'`) |
| 二维码过期用户再扫 | state expires_at 检查 + 提示"二维码已过期,请刷新" |
| OAuth secret 泄到 git | .env.example 不写真值,加 .env 入 .gitignore (现状已 OK) |

---

## 6. 不在本次范围

- 微信公众号/小程序 (P5-4 范围)
- 微信支付 (P5-3 范围)
- 钉钉/飞书扫码 (后续 Phase)
- 自动绑定邀请 (有邀请 link 时扫 → 自动加 org)
