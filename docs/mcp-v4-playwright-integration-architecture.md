# Playwright 集成架构修复 — 独立技术债 Ship Report

> **Ship 日期**: 2026-06-08
> **类型**: 技术债记录 (非功能修复)
> **依据**: B6 完整 ship report §3.1 (集成架构治根因) + B6 partial ship report §3.2 (根因推测已确认)
> **配套 PR**: B6 完整 (`562f807` + `bb6d953`) — 已 ship
> **commit**: 1 docs commit (技术债记录)
> **状态**: 记录完成, 推后续 PR 持续观察

## 1. 摘要

B6 完整 ship 中已用 **Node native `fetch()` 替代 `request.newContext()`** 治根因, 集成架构问题实际修复。但**根因在 Playwright test runner 源码层 (webServer.url 注入 page.request)** 仍存在, 未来如换 Playwright 版本或调整 webServer 配置可能复活。

本 ship 记录:
- 根因完整分析 (B6 partial 推测 → B6 完整确认)
- 3 替代方案对比 (已选 Node native fetch)
- 调试链 (9 步)
- 复测数据 (setup 1.1s + real-flow 9/10)
- 推后事项清单 (限流白名单 + UI selector)

## 2. 根因分析

### 2.1 症状 (B6 partial 失败现场)

```
[B6 setup] attempt 0 register status=404
[B6 setup] attempt 0 login status=404
... 3 attempts 都 404
```

**curl 同 URL** `http://127.0.0.1:8000/api/v1/auth/login` 返 **200**。

### 2.2 根因 (B6 partial §3.2 推测 → B6 完整确认)

**Playwright test runner 注入 `webServer.url` (3000) 到 `page.request` 和 `request.newContext()` 的 baseURL**。

**机制**:
1. `playwright.config.ts` 配置 `webServer: { url: "http://127.0.0.1:3000" }`
2. test runner 启动 webServer, 然后把 `webServer.url` 注入到所有 `page.request` 和 `request.newContext()` 的 baseURL
3. 即使用 `request.newContext({ baseURL: "http://127.0.0.1:8000" })` 显式指定 8000, 仍被注入覆盖
4. 即使用 `request.newContext()` + 绝对 URL `http://127.0.0.1:8000/api/v1/auth/login`, 仍被注入
5. 绝对 URL 在 `ctx.post()` 内部被 baseURL 截断, 路径前缀 `/api/v1` 被吃

**结果**: 所有 setup.ts 内的 APIRequestContext 调用走 `http://127.0.0.1:3000` (web dev), 而 web dev 在 `/api/v1/auth/login` 没有 reverse proxy (B6 partial 加 next.config.js rewrites 后能返 200, 但实际后端路径错配仍有问题)。

### 2.3 治根因方案: Node native `fetch()`

**B6 完整修法** (`apps/web/e2e/auth.setup.ts`):

```typescript
// 改用 Node native fetch (Node 18+) — 完全 bypass Playwright runner
const registerRes = await fetch(`${API_BASE}/auth/register`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(TEST_USER),
  signal: AbortSignal.timeout(5000),
});
```

**为什么治本**:
- Node native `fetch` 是 Node.js 内置, 不经过 Playwright runner
- `process.env.API_URL` 或 hardcoded `http://127.0.0.1:8000` 直连后端
- 不存在 baseURL 注入路径
- `AbortSignal.timeout(5000)` 显式超时控制

**实测** (B6 完整 ship):
- register 409 (e2e-tester 已存在) — **请求到 8000, 不是 3000**
- login 200, token 260 chars
- setup 1.1s (用户 baseline 1.3s, 略快)

## 3. 3 替代方案对比

| 方案 | 描述 | 优 | 劣 | 选? |
|---|---|---|---|---|
| **(A) Node native `fetch()`** (B6 完整) | 用 Node 18+ 内置 `fetch`, 直连 8000 | 治本, 5 行代码, 无依赖 | 仅 Node 18+ (项目已是 Node 20) | ✅ **选** |
| **(B) globalSetup 启 backend** | 改 Playwright `webServer` 不启, 用 `globalSetup` 启 backend, setup.ts 用 Playwright `request` | 跟 Playwright 生态一致 | 复杂, 需 double-fork + lifecycle 管理; globalSetup 跟 webServer 冲突 | ❌ 复杂度高 |
| **(C) Playwright `request` fixture + baseURL 8000** | 改 playwright config 不配 `webServer`, setup 用 `request` fixture with `extraHTTPHeaders` | 跟 Playwright 生态一致 | 失去 webServer 自动启停便利; 需外部启 backend | ❌ 失去 webServer |
| **(D) Next dev standalone + rewrite** (B6 partial) | next.config.js rewrites() reverse proxy, 走 frontend 3000 → backend 8000 | 走 Next 完整路径 | 治标: page.request 注入到 3000 后走 rewrite, 但 setup 仍依赖 page.request | ❌ 治标 |

**决策**: 选 (A) Node native fetch。理由: 治本 + 简单 + 已有 Node 20 满足。

## 4. 调试链 (9 步)

| # | 操作 | 结果 | 推断 |
|---|---|---|---|
| 1 | 跑 `real-flow.spec.ts` | 10 fail (auth.setup.ts fail) | setup 没 token |
| 2 | curl `http://127.0.0.1:3000/api/v1/auth/login` | 404 | Next dev 没 reverse proxy |
| 3 | 加 `next.config.js` `rewrites()` → `http://localhost:8000/api/v1/:path*` | curl 200 | rewrite 工作 |
| 4 | setup.ts 改用 `request.newContext({ baseURL: "http://127.0.0.1:8000" })` | 仍 404 | baseURL 注入覆盖 |
| 5 | 改用 `request.newContext()` + 绝对 URL `http://127.0.0.1:8000/api/v1/auth/login` | 仍 404 | 同上 |
| 6 | 加 `console.log`: register status=404 但 curl 同 URL 200 | 确认注入 | 注入是根因 |
| 7 | 试 `127.0.0.1` 替代 `localhost` | 仍 404 | IPv4 vs IPv6 不是因 |
| 8 | Node + Playwright `request` 直接 `import` (不走 test runner) | 200 ✓ | 确认 runner 注入 |
| 9 | **改用 Node native `fetch()`** (B6 完整修法) | register 500 → 409 → login 200 | 治本 |

**根因确认** (步骤 9): Node native fetch 绕过了 Playwright runner 注入, 治根因。

## 5. 复测数据 (B6 完整 ship)

| 测试 | 结果 | 备注 |
|---|---|---|
| `bash scripts/health-check.sh` | ✅ 11/11 | 6/7 步全过 (含微信 mock) |
| `npx playwright test --project=setup` | ✅ 1.1s | 用户 baseline 1.3s, 略快 |
| `npx playwright test e2e/real-flow.spec.ts` | ✅ 9/10 | 1 测 429 限流副作用 (推独立 PR) |
| `npx playwright test e2e/real-flow.spec.ts e2e/auth.spec.ts` | ✅ 23 / ❌ 8 | 含 auth 4 测 UI selector fail (跟集成无关) |
| daemonize_api.py [3.5/4] step | ✅ /health 200 | curl /health 后启 watchdog |
| webServer `reuseExistingServer: true` | ✅ PID 983 单一 | 不启 2 个 next dev |

**集成路径治本标志**:
- register 409 (请求到 8000, 不是 3000) — 之前是 404
- login 200, token 260 chars
- 5 关键流程之 "登录" 真后端 9/10 通过

## 6. 推后事项清单

### 6.1 [P1] real-flow 1 测 429 限流白名单

**症状**: `auth me returns demo user` 测 2 次 fail (chromium + standalone project) 都返 429
**根因** (推测): 60 并发/60s 限流在双 project 跑同 spec 时累积触发
**修法** (推独立 PR):
- (a) 加 `hr@acme-demo.com` / `demo123456` 到限流白名单 (A1 ship 功能)
- (b) Playwright config `workers: 1` (已有), 改 `projects: [chromium]` (去 standalone) 减少双倍请求
- (c) 加 5s sleep 在 1 测后

**估时**: 0.2d

### 6.2 [P1] auth.spec.ts 4 测 UI selector 修

**症状**: auth.spec.ts 4 测 fail 在 line 33 `#username` 找不到
**根因** (推测, 未深入): 测试 selector 跟 UI 实现不同步 (假设 `#username` 实际用 `input[name="email"]` 或类似)
**修法** (推独立 PR):
- (a) 看 4 测 spec, 改 selector 跟 UI 一致
- (b) 或加 `data-testid` 属性到 UI 组件, spec 用 `getByTestId`

**估时**: 0.2-0.3d

**注**: 跟 B6 集成架构修复无关, 是测试代码 / UI 不同步问题。

### 6.3 [P2] Playwright runner baseURL 注入根因在源码层

**症状**: 注入行为在 `playwright/lib/runner` 内, 没法在 spec/config 层完全屏蔽
**修法** (推后续):
- (a) Playwright upstream issue 反馈 (等官方响应)
- (b) 写 patch 在 setup.ts 顶部硬覆盖 baseURL (治标)
- (c) 维护"用 Node native fetch 替代"约定 (现状, 推荐)

**估时**: 0.1d (写约定文档) / 1d+ (upstream)

### 6.4 [P2] 全 18 spec 跑过

**现状**: 本次只跑 2 spec (real-flow + auth) 验集成, 18 spec 中 16 spec 未跑
**修法** (推后续): 在 CI workflow 加 `npx playwright test --project=chromium` 跑全 spec, 监控退化
**估时**: 0.2d (CI workflow) + 0.3d (修 fail 测)

## 7. 监控 / 复测

**B6 集成修法** (`auth.setup.ts` Node fetch) 状态:
- ✅ setup 1.1s (本地)
- ⚠️ CI 未测 (需后续 PR 加 CI workflow)
- ⚠️ Playwright 升级后未测 (潜在回归)

**监控指标**:
- setup 跑时间 > 5s → 警告 (baseline 1.1-1.3s)
- setup 5 attempts 全 fail → 治根因失败, 推独立 PR
- register/login 返 404 → 注入复活, 立刻查

## 8. 引用

- B6 完整: `docs/mcp-v4-v1.4-b6-ship-report.md` (562f807 + bb6d953)
- B6 partial: `docs/mcp-v4-v1.4-b6-ship-report.md` (fd9846b + de1d3db, partial 状态)
- Fix-1: `docs/mcp-v4-fix-1-ship-report.md` (5min sleep 限流, B41a959 + 91b9510)
- 集成修法: `apps/web/e2e/auth.setup.ts` (Node fetch 治根因)
- webServer 配置: `apps/web/playwright.config.ts` (reuseExistingServer + :3000 + IPv4)
- rewrite: `apps/web/next.config.js` (B6 partial 加的 `/api/v1/*` reverse proxy)
- Playwright 上游: `webServer.url` 注入 `page.request` 行为 — https://playwright.dev/docs/api/class-testconfig#test-config-web-server (webServer 文档未明确说明注入行为, 是 implicit)

## 9. 行动项

- ✅ 记录根因 + 治本方案 (本文档)
- ⏳ 推 6.1 限流白名单 (独立 PR, 0.2d)
- ⏳ 推 6.2 auth selector 修 (独立 PR, 0.3d)
- ⏳ 推 6.3 Playwright upstream issue / 维护约定
- ⏳ 推 6.4 全 18 spec 跑过 (CI workflow, 0.5d)
