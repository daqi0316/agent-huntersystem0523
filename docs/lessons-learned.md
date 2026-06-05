# Lessons Learned — ContextBar P1 阶段（T1-T7）

> 沉淀 8 个 commits 的关键决策与避坑点，给未来接手的 agent/人。
> 时间窗: 2026-06-04 ~ 2026-06-05,17-21 天 plan 中的 P0+P1 部分。

## 0. 工程铁律（先于一切决策）

源自 CLAUDE.md + 本次教训:

1. **改完 = `bash scripts/health-check.sh` 9/0 pass**,不跑不算完
2. **Bash 后台进程 = 死**。任何"真后台"(API server、watchdog) 必须 Python double-fork (`make api:dev` / `make api:watch`)
3. **e2e 跑 production build** (`./node_modules/.bin/next build && next start`),不跑 dev server。dev 编译 `/_not-found` 会破坏已编译路由
4. **uvicon 进程只 listen IPv4** — httpx 必须 `127.0.0.1` 而非 `localhost` (否则命中 ::1 IPv6 失败)
5. **uvicon 必须 `--reload`** — 否则改 model/枚举后,旧进程仍用旧字节码,出现"代码已修但生产仍 500"假象
6. **TypeScript `as any` / `@ts-ignore` / `@ts-expect-error` 永不用** — 用 type guard / type narrowing 替代
7. **Bugfix Rule**: 修 bug 不顺带 refactor,最小 diff
8. **comment/docstring 钩子**: 优先 self-explain code,少注释。注释必要场景: (a) 已有注释 (b) BDD given/when/then 格式 (c) 复杂算法/性能/安全边界

## 1. T1: Monorepo 真正独立包 (commit 066da08)

### 教训 1.1: "用文件" ≠ "用包"

提取 `apps/web/components/common/context-bar` 到 `packages/context-bar` 时,仅移动文件不够。要做到:

- **三层架构分离**: `agent-store` (数据) + `context-bar` (UI) + `apps/web` (host 注入业务)
- **unbuild 配置**: ESM + CJS + `.d.ts` + `sideEffects: false` + sourcemap
- **peerDeps 完整**: react / zustand / next / lucide-react / clsx / tailwind-merge
- **host 业务回调通过 props 注入**: `onApprovalApprove` / `onApprovalReject` (包内不调 host 私有路径)
- **tsconfig lib**: 包内有 browser 代码 (window / crypto),加 `"lib": ["DOM", "DOM.Iterable", "ES2022"]`
- **CSS**: unbuild 不处理 CSS,消费方 tailwind `content` 必须 scan `node_modules/@ai-recruitment/context-bar/dist/**/*.{js,cjs,mjs}`

### 教训 1.2: monorepo 内消费用 symlink + dist

`apps/web/node_modules/@ai-recruitment/context-bar` 是 symlink → `packages/context-bar`。
源码改动后必须 `corepack pnpm --filter @ai-recruitment/context-bar build` 重新打 dist,apps/web 进程才能 pick up。

## 2. T2: 跨抽屉导航 (commit aad9d2c)

### 教训 2.1: 详情页 `/candidates/[id]` 替代 6 重路由

不要为每个详情类型建独立子路由。统一:
- `apps/web/app/(dashboard)/candidates/[id]/page.tsx`
- `apps/web/app/(dashboard)/jobs/[id]/page.tsx`
- URL 加 `?focus=<id>` + `?prefill=<text>` 携带跨抽屉状态
- 目标元素 `scrollIntoView({ behavior: "smooth" })` + 1.5s ring 高亮

## 3. T3: Redis Streams 持久化 (commit 7483689)

### 教训 3.1: SSE 三层通道 = 内存 + Redis pub/sub + Redis Streams

降级顺序:
1. 内存 pub/sub (进程内,最快)
2. Redis pub/sub (跨进程,无持久化)
3. Redis Streams (跨进程 + 持久化,客户端 Last-Event-ID 重放)

**为什么需要 Streams**: 客户端断开 > 1 分钟后,SSE 自动重连会丢断线期间的事件。Streams 持久化 + `XADD` + `XREAD FROM <last_id>` 让客户端从断开点重放,不掉数据。

### 教训 3.2: 节流器在 send 端

`emit_ai_notification` 同 user × kind 1s 内 ≤ 1 条。防批量更新风暴淹没客户端。

### 教训 3.3: 跨进程 Redis 客户端共享陷阱

`test_agent_events_e2e_redis_integration.py` 3 skip,因跨 pytest event loop 共享 Redis client 会冲突。**机制由单元测试覆盖**(单进程 event loop 测),集成测试只验"端到端 wire 通"。

## 4. T4: 详情抽屉 (commit 3a7d748)

### 教训 4.1: React 18 strict mode 双 mount 死锁

`use-candidate-detail` hook 在 `useEffect` 里设了 `lastFetchAtRef.current = Date.now()` + 500ms debounce。
React 18 dev strict mode 故意双 mount,导致:
- mount 1: set ref = T0
- cleanup: 设 isMountedRef = false
- mount 2: set ref = T1 (但 isMountedRef 还是 false!)

修: `cleanup` 必须 `lastFetchAtRef.current = 0` 重置 ref,且 `useEffect` 内 `if (!isMountedRef.current) return;` 不只是 cleanup 判。

### 教训 4.2: 业务/UI 分离 — PendingApprovalSection 不调 host API

包内 PendingApprovalSection 接受 `onApprove` / `onReject` props,`apps/web/components/common/header.tsx` 注入 `api.post("/human-loop/approve", ...)`。**包不依赖 host 私有路径**,保持可独立发布。

### 教训 4.3: Playwright e2e selector 经验

- 中文 `i` flag 在 `aria-label*="看板" i` 中**不工作** (中文无大小写) — 改用 `[aria-label*="看板"]`
- 完整 URL > glob `**` > regex — glob 经常不命中
- mock `page.route` 不总是生效 — 改用真实后端 seed 数据 (e.g. `candidate "Bob"`)
- `addInitScript` + `localStorage` 注入 token + seed 状态时,必须 override `setItem` 防止 zustand persist 覆盖

## 5. T5: 拖拽/搜索/导出 (commit 3c7163b)

### 教训 5.1: 拖到 body 外 = 天然回滚

React 不会在 body 触发 `onDrop` 事件。**不需要手动回滚代码** — 现有 `handleDrop` 仅在 DataCardItem 上注册,body drop 不会改 state。
加一个 `handleDragEnd` 显式清视觉状态 (draggingId/dragOverId) 即可。

### 教训 5.2: URL hash 同步排序,跨 tab 共享顺序

`#cards=id1,id2,...` ≤50 id 截断 (防 8192 字符 URL 上限)。**跨设备不**用 BroadcastChannel (per-session,URL hash 即可;跨设备语义不对)。

### 教训 5.3: 重复定义 trap — `handleDrop` 加完老版本还在

我两次 edit 都加了 `handleDrop`,build 报 "already declared"。**关键**: edit 时确认 old block 已删除,不要"加新版"覆盖"删老版"两步走,容易留垃圾。

## 6. T6: 埋点 + /metrics (commit f98b57a)

### 教训 6.1: 端点可配置 — 相对 URL 404 bug

最初 `fetch("/api/v1/agent/telemetry", ...)` 在 Next.js 3007 上跑,fetch 把相对 URL 解析到 3007 (frontend) 而非 8000 (backend) → 404。

修: 加 `setTelemetryEndpoint(url)`,host (apps/web layout `<TelemetryBoot>`) 启动时调:
```ts
const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
setTelemetryEndpoint(`${base}/agent/telemetry`);
```

### 教训 6.2: route.template 防 prom cardinality 爆炸

`request.url.path` 在 `/api/v1/candidates/{uuid}/jobs` 会爆 (每 UUID 单独 label)。
改用 `request.scope["route"].path` (FastAPI matched template) — 所有 UUID 归到 `/api/v1/candidates/{candidate_id}/jobs` 一个 label,cardinality 可控。

### 教训 6.3: 客户端/后端白名单双向保护

恶意事件 `malicious_xx` 在前端被白名单过滤 (console.warn + 不发),后端再过 ALLOWED_EVENTS 兜底(rejected += 1)。**不能省前端过滤** — 不然埋点流量被恶意利用爆 prom label 空间。

### 教训 6.4: PII 过滤 — 客户端先剥

`query: "test@example.com"` 不在 ALLOWED_PROPS,客户端先剥,后端收到的 props 是空的 (只有 `result_count: 5`)。**前端不依赖后端过滤,后端过滤是兜底**。

### 教训 6.5: 单例状态污染测试

`createTelemetryQueue()` 返回单例,模块级 `_queue` / `_seen` / `_destroyed` / `_flushTimer` 共享。测试 destroy 一个 queue 影响所有后续测试。

修: 加 `__resetTelemetryStateForTests()`,每个 `test` 用 `beforeEach` 重置。**测试单例 module-level 状态必加 reset helper**,这是 zustand / 全局 queue / 任何带 module state 的代码共有的问题。

## 7. T7: ErrorBoundary + SSE 解析容错 (commit 281aa64)

### 教训 7.1: 颗粒化 ErrorBoundary 树

```
<ErrorBoundary "ContextChip">      ← 独立
  <ContextChip />
</ErrorBoundary>
<ErrorBoundary "ContextDrawer">    ← 独立
  <ErrorBoundary "CurrentContext"> ← section 独立
  <ErrorBoundary "Notifications">   ← section 独立
  <ErrorBoundary "PendingApproval">← section 独立
  ...
</ErrorBoundary>
```

任一挂不影响其他。**不要只在外层包一个** — 抽屉挂会把整个上下文树带走。

### 教训 7.2: try/catch 静默 fallback 必须上报

`use-event-source.ts:121` 原本 `try { handler(JSON.parse(...)) } catch { handler(e.data) }` 静默 fallback,生产中无法观测。修: 调 `telemetryQueue.track("sse_parse_error", ...)`,后端 /metrics 暴露 `frontend_event_total{event="sse_parse_error",source="use-event-source"}` 计数。**静默 fallback + 可观测 = 工业级**。

## 8. 通用工程模式

### 8.1: commit message 长度

文件 base 提交 (`git commit -F /tmp/x.md`) 适合:
- 中文含引号
- 详细 commit body (含决策、验证、原因)
- > 1 段说明

`-m "短"` 适合 trivial change (typo、formatting)。

### 8.2: tsc 在 monorepo 跑

- `apps/web` tsc 涵盖全 host 代码,跑这个够 (它 include `node_modules/@ai-recruitment/*` via symlink)
- `packages/agent-store` tsc 单独跑,检查 .d.ts 完整性 + DOM lib 配置
- `packages/context-bar` 同上

### 8.3: E2E 跑 production build (非 dev)

dev 编译 `/_not-found` / `/_error` 会破坏已编译路由 (Next.js 14 已知 bug,2026-06 多次踩)。
流程: `pnpm build` → daemonize `next start -p 3007` → 跑 `verify-*.ts` → 留 daemon 在后台。

### 8.4: 健康检查 = 9/0

```
1. 基础设施: postgres/redis/qdrant/minio
2. 后端进程: uvicorn 8000
3. 后端可登录: POST /auth/login
4. 后端可验证: GET /auth/me 带 token
5. 前端可达: GET /login + /agent + _next chunk
6. 端到端登录: verify-login-e2e.ts (真实后端)
```

任一失败 = 系统不可用 = 改完不算。

### 8.5: Docker 镜像源

`docker.m.daocloud.io` 而非 `docker.io` (后者在国内经常 timeout)。
compose 启动前先看 `lsof -i:5432 -i:6379 -i:6333 -i:9000` 确认 LISTEN,再起后端。

## 9. 待办 (P2 候选)

| 优先级 | 任务 | 价值 | 风险 |
|---|---|---|---|
| P2-1 | 移动端响应式 (drawer 改 bottom sheet < 768px) | UX P0 gap | 中 (要改 ContextDrawer 布局 + state) |
| P2-2 | IndexedDB telemetry fallback (硬崩不丢) | 数据完整性 | 中 (IndexedDB 异步 + quota) |
| P2-3 | Cross-package 集成 e2e | 防回归 | 低 (沿用 T4 模式) |
| P2-4 | Prometheus 告警规则 (gauge > 50 / 5xx > 1%) | 运维 | 低 (写 prom rules 文件) |
| P2-5 | SSE auth token rotation | 安全 | 高 (SSE 长连接鉴权复杂) |

## 10. 一句话总结

> 工业级 = 颗粒化错误隔离 + 客户端/后端双向白名单 + 可观测 metrics + 完整 test pyramid。
> 稳定开发 = 改完跑 health-check 9/0 + e2e 跑 production build + 错误时降级而非崩溃。
> 全局规划 = monorepo 边界清晰 + 文档沉淀 (本文件) + 决策可追溯。
