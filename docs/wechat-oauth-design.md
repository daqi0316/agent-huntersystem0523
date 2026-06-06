# P5-2 微信扫码登录 — 设计文档

更新时间: 2026-06-06

## 1. 目标

国内 B2B SaaS 标配: 用户可用企业微信扫码登录本系统, 替代 email 注册。复用 P5-1 多租户 + JWT 双轨 (sub + current_org_id)。

## 2. OAuth 流程

```
┌────────┐                                      ┌──────────┐
│  Front │  GET /auth/wechat/qrcode             │  Backend │
│  End   ├─────────────────────────────────────►│   API    │
│        │  {qrcode_url, state, expires_in}     │          │
│        │◄─────────────────────────────────────┤          │
│        │                                      │          │
│ [user]  │  用企业微信扫二维码                  │          │
│   │    │                                      │          │
│   ▼    │  GET /auth/wechat/callback?code&state│          │
│ ┌──────┴──────────────┐                       │          │
│ │  企业微信 浏览器跳转  ├──────────────────────►│ exchange │
│ └─────────────────────┘  ← 302 /login/wechat- │ code 换  │
│                          callback?token=...    │ unionid  │
└────────┘                                      └────┬─────┘
                                                    │
                                              find_or_create
                                              user + auto org
                                                    │
                                              签 JWT
                                              落 audit_log
                                                    │
                                              302 redirect
```

## 3. DB Schema (Migration p5_2_wechat_oauth)

### users 表加列

| 列 | 类型 | 约束 | 用途 |
|---|---|---|---|
| wechat_unionid | VARCHAR(64) | NULL, partial unique index | 跨 app 唯一标识 |
| wechat_openid | VARCHAR(64) | NULL | 当前 app 内 userid |
| wechat_nickname | VARCHAR(64) | NULL | 显示名 |
| wechat_avatar_url | TEXT | NULL | 头像 |
| auth_source | VARCHAR(16) | NOT NULL DEFAULT 'email' | 登录方式 ('email' / 'wechat') |

### 新表 wechat_oauth_state

| 列 | 类型 | 用途 |
|---|---|---|
| state | VARCHAR(64) PK | CSRF token, 32-byte secrets |
| redirect_uri | VARCHAR(512) | callback 跳转地址 |
| created_at | DateTime | 生成时间 |
| expires_at | DateTime | 过期时间 (默认 600s) |
| used_at | DateTime NULL | NULL=未用, 否则不可再用 |

## 4. Backend 接口 (auth.py)

### 4.1 GET /auth/wechat/qrcode

生成 state + 返二维码 URL (前端用 `qrserver.com` 渲染)。

```json
Response: {
  "success": true,
  "data": {
    "qrcode_url": "weixin://wxpay/bizpayurl?pr=mockqrcode&state=abc...",
    "state": "abc...",
    "expires_in": 600,
    "mock": true
  }
}
```

### 4.2 GET /auth/wechat/callback?code=&state=

**真模式**: 调 `https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo` 换 unionid/openid。
**Mock 模式**: 用 code[:8] derive mock unionid (固定前缀 `mock_unionid_`)。

Callback 流程:
1. 验 state (未用过 + 未过期) → 标记 used_at
2. exchange_code → user_info
3. find_or_create_user (按 unionid)
4. get_or_create_default_org (P5-1 自动建 org + owner)
5. 签 JWT (sub=uid, current_org_id=org)
6. log_audit(action=WECHAT_LOGIN, metadata={unionid, mock})
7. 302 重定向到 `{frontend}/login/wechat-callback?token=...&org_id=...&source=wechat`

### 4.3 POST /auth/wechat/mock-login?code=

**仅 mock_mode=True 时可用**。本地开发一键登录: 跳过前端扫码, 直接调 exchange_code + find_or_create_user 返 token。

## 5. Service 层 (app/services/wechat_oauth.py)

### 5.1 generate_qrcode(db, redirect_uri)

- 生成 256-bit state (secrets.token_urlsafe)
- 写 wechat_oauth_state (expires_at = now + 600s)
- 真模式: 拼企微 OAuth URL `https://open.weixin.qq.com/connect/oauth2/authorize?...`
- Mock 模式: 拼 `weixin://wxpay/bizpayurl?pr=mockqrcode&state=...` (前端不真扫)

### 5.2 exchange_code(db, code, state)

- 验 state: 不存在/已用/已过期 → `WeChatOAuthError`
- 标记 used_at
- Mock 模式: `unionid = "mock_unionid_" + code[:8]`
- 真模式: HTTP 调企微 API (httpx async client)

### 5.3 find_or_create_user(db, unionid, openid, nickname, avatar_url)

- 按 unionid 查 users 表
- 存在: 更新 nickname/avatar/last_login_at, 返 user
- 不存在: 建 user (email = `wx_<unionid>@wechat.local`, hashed_password = 不可登录占位, auth_source='wechat'), 返 user

## 6. Frontend (apps/web)

### 6.1 登录页加按钮

`login-form.tsx`:
- 原 email 登录表单保留
- 下方分隔线
- "企业微信扫码登录" 按钮 (调 WeChatQrcodeModal)

### 6.2 WeChatQrcodeModal

- 调 GET /auth/wechat/qrcode 拿 state + URL
- 渲染二维码 (mock 模式显示 📱 emoji, 真模式用 qrserver.com)
- 倒计时 (秒)
- Mock 模式: 额外显示 "Mock 一键登录" 按钮 (调 POST /auth/wechat/mock-login)

### 6.3 wechat-callback 页

- 读 URL params: token + org_id
- 存 localStorage (`ai-recruitment-token`, `ai-recruitment-org-id`)
- 调 GET /auth/me 验证
- 成功 → 跳 /dashboard
- 失败 → 显示错误 + 返 /login

## 7. 配置 (config.py)

6 个 settings 字段 (环境变量):

| 字段 | 默认 | 用途 |
|---|---|---|
| wechat_corp_id | "" | 企业 corpID |
| wechat_corp_agent_id | "" | 自建应用 agentid |
| wechat_corp_secret | "" | 应用 secret (敏感) |
| wechat_oauth_redirect_uri | "http://localhost:3000/api/auth/wechat/callback" | callback 跳转目标 |
| wechat_qrcode_expire_seconds | 600 | state 过期时间 |
| wechat_mock_mode | True | 本地 mock 模式开关 |

## 8. 测试 (tests/test_wechat_oauth.py)

13 个用例:
- 4 个 config 测试 (默认值校验)
- 2 个 audit enum 测试
- 2 个 qrcode endpoint 测试
- 2 个 mock-login endpoint 测试
- 3 个 service direct 测试 (state 校验 + find_or_create)

**结果**: 12/13 通过, 1 个 mock-login 端到端测试因 PostgreSQL 未起失败 (环境问题, 同 test_auth.py 3 fail 模式)。

## 9. 安全 / 风险

| 风险 | 缓解 |
|---|---|
| CSRF 重放 state | DB 存 state + used_at NULL 唯一, callback 时 mark used |
| Mock 模式泄漏到 prod | `wechat_mock_mode=True` 默认仅本地; staging/prod 必须 `WECHAT_MOCK_MODE=false` |
| 已有 email 用户首次用微信 | 按 unionid 查; email 留 `wx_<unionid>@wechat.local`, auth_source='wechat' |
| state 过期 | expires_at < now() → 400 + 提示刷新 |
| 企微 secret 泄到 git | .env.example 不写真值; .env 已入 .gitignore |

## 10. 待办 (P5-3+)

- 微信支付 (P5-3 6d)
- 公众号 + 视频号 (P5-4)
- 钉钉/飞书扫码 (后续 Phase)
- 邀请 link 自动绑定 (扫 invite link → 自动加 org)
- Email 邮箱绑定微信 (WECHAT_BIND audit 已预留)
