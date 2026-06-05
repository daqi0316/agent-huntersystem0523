# 错误处理矩阵（T7 实施）

> ContextBar / SSE / localStorage / 后端 API / Redis 五类错误的处理策略。
> 配套代码：`packages/context-bar/src/error-boundary.tsx` + `apps/web/hooks/use-event-source.ts` + `apps/web/hooks/chat/use-chat-messages.ts` + `apps/api/app/core/redis.py`

## 1. ContextBar UI 错误（T7 颗粒化 ErrorBoundary）

| 失败位置 | 降级行为 | 用户可见 | 上报 |
|---|---|---|---|
| `ContextChip` 子树 | fallback div + retry → openDrawer | chip 区域显示"该区域出现异常 · 重试" | `error_boundary{source="ContextChip"}` |
| `ContextDrawer` 子树 | fallback "抽屉加载失败 — chip 仍可点击重试" | drawer 区域固定 div 提示，**chip 仍可点** | `error_boundary{source="ContextDrawer"}` |
| 6 个 section (CurrentContext/Notifications/PendingApproval/SessionStats/RecentActivity/QuickActions) | fallback "该区域出现异常 · 重试" | 仅该 section 不可用，其他 section 正常 | `error_boundary{source="<section>"}` |
| `SearchBar` | fallback 文本输入（未来 P2） | 搜索/过滤不可用，data cards 仍可见 | `error_boundary{source="SearchBar"}` |

**解耦原则**：

```
┌─────────────────────────────────────────────────┐
│  Host 页面 ErrorBoundary (apps/web, 全局兜底)   │
│  └─ <ContextBar>                                │
│     ├─ <ErrorBoundary "ContextChip">            │ ← 独立
│     │  └─ <ContextChip />                       │
│     └─ <ErrorBoundary "ContextDrawer">          │ ← 独立
│        ├─ <ErrorBoundary "CurrentContext">      │ ← 独立
│        ├─ <ErrorBoundary "Notifications">        │
│        ├─ <ErrorBoundary "PendingApproval">     │
│        └─ ...                                   │
└─────────────────────────────────────────────────┘
```

## 2. SSE 实时流错误

| 失败模式 | 触发点 | 处理 | 上报 |
|---|---|---|---|
| EventSource 连接失败 (401/403/5xx) | `useEventSource` open | `connected=false` + 浏览器自动重连 | 无（连接状态自描述） |
| EventSource 网络断开 | `useEventSource` onerror | 浏览器自动重连（同源） | 无 |
| SSE message JSON.parse 失败 | `useEventSource.subscribe` wrapped handler | `try/catch` → 回调 `handler(e.data)` (raw 字符串) + `console.warn` + telemetry | `sse_parse_error{source="use-event-source"}` |
| SSE message 业务 schema 错（结构对但字段缺） | `handler` 内部 | 业务方 try/catch（`use-chat-messages` 等） | 由业务方决定 |
| Last-Event-ID 持久化失败（localStorage 满/禁用） | `saveLastEventId` | silent fallback (try/catch) | 无（fire-and-forget） |

## 3. localStorage 错误

| 失败模式 | 触发点 | 处理 | 上报 |
|---|---|---|---|
| localStorage 不可用（隐私模式） | 任意 `localStorage.getItem` | `try/catch` → 返默认空值 | 无 |
| JSON.parse 失败（数据被外部破坏） | `use-chat-messages.loadMessages` / `use-event-source.loadLastEventId` | `try/catch` → 返 `[]` / `null` + `localStorage.removeItem(key)` | `sse_parse_error{source="use-chat-messages"}` (仅 chat-messages) |
| zustand persist rehydrate 失败（partialize 字段 schema 不匹配） | `useAgentStore` 启动 | zustand 内置 try/catch → 走初始 state | 无（zustand 默认行为） |
| quota exceeded（写入超限） | `setItem` | 静默 swallow（持久化是 best-effort） | 无 |

## 4. 后端 API 错误

| 失败模式 | 触发点 | 处理 | 上报 |
|---|---|---|---|
| 业务 4xx (400/401/403/404) | tRPC/Fetch | 业务方 try/catch + toast 提示用户 | 无（用户行为可恢复） |
| 业务 5xx | tRPC/Fetch | 业务方 try/catch + "服务异常，请稍后重试" | 无 |
| 限流 (429) | 全局中间件 `create_rate_limit_middleware` | 返 429（host UI 提示） | `api_request_total{status="429"}` |
| `/metrics` 端点本身错 | 任何内部 | `Response(status=500, body="")` | 无（避免递归） |
| `/metrics` prom-client 内部错 | `generate_latest` | 透传 500 | 无 |
| telemetry 端点批量 > 100 | pydantic | 422 | `telemetry_received_total{status="error"}` (前端有 retry 时) |

## 5. Redis / 后端基础设施

| 失败模式 | 触发点 | 处理 | 上报 |
|---|---|---|---|
| Redis ping 失败 | `redis_client.ping()` (lifespan) | `redis_connected=false` (JSON) — **当前 /metrics 端点未返此字段** | 无 |
| Redis 写入失败 (SSE 持久化) | `agent_events.py` emit | log warning + 走内存 pub/sub fallback | 无（无 metric 暴露） |
| LLM 调用失败 (chat agent) | `apps/api/app/llm/retry.py` | exp backoff 3 次 + 返 503 | `api_request_total{status="503"}` |
| LLM 重试用尽 | `retry.py` after 3 attempts | 返 "模型暂时不可用" 用户提示 | `api_request_total{status="503"}` |
| Database 连接失败 | lifespan / handler | schema_audit fail = 阻止启动；handler 返 503 | `api_request_total{status="503"}` |
| Postgres enum/UUID 不一致 | schema_audit | 阻止启动（fail_on_mismatch=True） | 启动期 fail-fast，无 metric |

**T7.4 (Redis 断线重连指数退避) 当前状态：n/a**
- 后端只发不订阅（pub/sub 模式 = publisher），无重连需求
- 如未来引入 Redis subscriber，需补 `redis.asyncio.Redis(retry=Retry(ExponentialBackoff(...)))`

## 6. 前端构建/部署错误

| 失败模式 | 触发点 | 处理 | 上报 |
|---|---|---|---|
| JS chunk load 失败 (404) | Next.js 自动 retry | Next.js 内置 retry + 错误页 | 无（用户刷新解决） |
| hydration mismatch | React | 客户端 re-render (warning) | 无 |
| `_error` / `_not-found` 编译错 | Next.js dev | dev 已知 bug（CLAUDE.md 记录）—— 改用 production build | 无 |

## 7. 降级策略总表

| 优先级 | 失败时降级到 | 用户体验 |
|---|---|---|
| 1 | chip 不可用 → drawer fallback 提示"重试" | 核心 always-on |
| 2 | drawer 不可用 → chip 仍可见 | 核心 always-on |
| 3 | section 不可用 → 其他 section 仍渲染 | 部分降级 |
| 4 | SSE 断开 → 重连 + 不影响 UI | 静默降级 |
| 5 | localStorage 错 → 内存 state | 刷新丢数据 |
| 6 | LLM 错 → "服务异常" toast | 用户可重试 |
| 7 | Redis 错 → 内存 pub/sub fallback | 跨进程事件丢失 |
| 8 | DB 错 → 阻止启动 / 503 | fail-fast |

## 8. 监控指标覆盖

通过 `frontend_event_total{event="error_boundary"|"sse_parse_error"}` + `api_request_total{status=~"5..|429"}` 可观测：

- ErrorBoundary 触发频率（按 section）
- SSE 解析错频率（按 source）
- API 5xx 错误率（按 path）
- 限流触发频率（按 path）

## 9. 验收 checklist

- [x] ContextChip 独立 ErrorBoundary（drawer 挂 chip 仍可见）
- [x] ContextDrawer 独立 ErrorBoundary（chip 挂 drawer 仍可重试）
- [x] 6 个 section 颗粒化包装
- [x] SSE JSON.parse try/catch + telemetry 上报
- [x] chat-messages localStorage parse try/catch + removeItem + telemetry
- [x] 客户端/后端白名单双向保护
- [x] 4/4 ErrorBoundary 单元测试
- [x] 8/8 T7 E2E
- [x] health-check 9/0
- [n/a] BroadcastChannel 不可用 — 已在 `apps/web/lib/agent-store-sync.ts:49-51` 静默降级（`console.warn`），覆盖 T7.6
- [n/a] Redis 断线重连 — 后端只发不订阅，无重连需求（T7.4）
