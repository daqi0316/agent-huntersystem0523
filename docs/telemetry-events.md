# 埋点 + 指标参考表（T6 实施）

> Telemetry 事件名、Prometheus 指标名、props 白名单、错误处理矩阵。
> 配套代码：`packages/agent-store/src/telemetry-queue.ts` + `apps/api/app/core/telemetry.py` + `apps/api/app/api/agent_telemetry.py`

## 1. 端到端数据流

```
┌──────────────┐  track(event, props)   ┌──────────────────┐
│  context-bar │ ─────────────────────► │ telemetry-queue  │
│  (UI 层)     │   500ms throttle       │ (agent-store)    │
└──────────────┘   20 条/5s 批量        │ - 白名单过滤     │
                                        │ - props 过滤     │
                                        │ - sendBeacon 卸载│
                                        └────────┬─────────┘
                                                 │ POST /api/v1/agent/telemetry
                                                 │ (端点可配置: setTelemetryEndpoint)
                                                 ▼
                                        ┌──────────────────┐
                                        │ agent_telemetry  │
                                        │ (FastAPI)        │
                                        │ - ALLOWED_EVENTS │
                                        │ - sanitize_props │
                                        │ - record_event   │
                                        └────────┬─────────┘
                                                 │ prom-client
                                                 ▼
                                        ┌──────────────────┐
                                        │ /metrics         │
                                        │ (Prometheus 格式)│
                                        └──────────────────┘
```

## 2. 事件白名单（`ALLOWED_EVENTS`）

事件名前后端**强一致**。新事件必须同时更新：

- `packages/agent-store/src/telemetry-queue.ts` (前端白名单)
- `apps/api/app/core/telemetry.py` (后端白名单)

| 事件名 | 触发位置 | 含义 | 关键 props |
|---|---|---|---|
| `drawer_open` | context-bar `useEffect[open]` | 抽屉打开 | `source: "chip"` |
| `drawer_close` | context-bar `useEffect[open] cleanup` | 抽屉关闭 | `duration_ms: int` |
| `card_view` | context-bar DataCardItem 展开 | 卡片查看 | `card_type: string` |
| `card_export` | context-bar handleExport | 导出 JSON | `card_type`, `result_count` |
| `search_use` | context-bar `useEffect[query, activeTypes]` | 搜索/过滤 | `result_count`, `source: "query"\|"filter"` |
| `hash_order_change` | context-bar handleDrop | URL hash 更新 | `card_type`, `success: bool` |
| `drag_drop` | context-bar handleDrop | 拖拽完成 | `card_type`, `success: bool` |
| `keyboard_nav` | context-bar useCardKeyboardNav onActivate | 键盘激活 | `card_type`, `success: bool` |
| `approval_action` | context-bar PendingApprovalSection | 审批通过/拒绝 | `card_type`, `success: bool` |
| `notification_view` | context-bar NotificationsSection | 通知查看 | `card_type`, `success: bool` |
| `error_boundary` | context-bar ErrorBoundary componentDidCatch | React 错误边界触发 | `source: "ContextChip"\|"ContextDrawer"\|<section>`, `success: false` |
| `sse_parse_error` | apps/web use-event-source / use-chat-messages | SSE/JSON 解析错 | `source: "use-event-source"\|"use-chat-messages"`, `success: false` |

**约束**：
- 事件名 ≤ 64 字符（pydantic 校验）
- 单 batch ≤ 100 事件
- 客户端 throttle：同 event 500ms 内 ≤ 1 次
- 客户端 queue 上限 200 条（超截断最早）
- 后端白名单兜底：未知事件 → `rejected += 1`

## 3. props 白名单（`ALLOWED_PROPS`）

**仅以下字段被后端接受**（其他字段在客户端 + 后端双重过滤）：

| 字段 | 类型 | 含义 | 示例 |
|---|---|---|---|
| `card_type` | string | 业务分类标签 | `candidate_list` / `dashboard_stats` / `job_detail` |
| `duration_ms` | number | 持续时间 | `1200` |
| `success` | bool/string | 操作结果 | `true` / `false` |
| `source` | string | 触发源 | `chip` / `filter` / `query` |
| `result_count` | number | 计数（搜索/导出） | `5` |

**PII 过滤**（`sanitize_props` 同步执行）：

| 黑名单 | 匹配方式 | 例子 |
|---|---|---|
| Email | regex | `user@example.com` → 剥离 |
| 中国手机号 | regex `1[3-9]\d{9}` | `13800138000` → 剥离 |
| 国际电话 | regex | `+1 555-1234` → 剥离 |
| 字段名含 name/email/phone 等 | regex | `user_name`, `userEmail` → 整字段剥 |

## 4. Prometheus 指标（4 个）

`/metrics` 端点（GET）返标准 prom 文本格式（`text/plain; version=0.0.4`）。

### 4.1 `frontend_event_total` (Counter)

```
frontend_event_total{event="drawer_open",card_type="none",success="true"} 12
```

标签：
- `event`: 事件名（白名单内）
- `card_type`: 业务类型（无则 `none`）
- `success`: `true` / `false`

### 4.2 `telemetry_received_total` (Counter)

```
telemetry_received_total{status="accepted"} 38
telemetry_received_total{status="rejected"} 2
telemetry_received_total{status="filtered"} 0
```

标签：
- `status`: `accepted` (已记录) | `rejected` (白名单拒) | `filtered` (PII 全剥) | `error` (record 异常)

### 4.3 `api_request_total` (Counter, middleware)

```
api_request_total{method="POST",path="/api/v1/agent/telemetry",status="200"} 38
```

**重要**：用 `request.scope["route"].path` (matched template) 而非 `request.url.path` (raw) —— 防 UUID 路径参数爆 prom cardinality。

### 4.4 `telemetry_queue_size` (Gauge)

```
telemetry_queue_size 17
```

前端每次 flush 时上报当前队列容量（`len(batch.events)`）。用于观测前端堆积情况。

## 5. 错误响应

`POST /api/v1/agent/telemetry` 异常路径：

| 情况 | HTTP | body |
|---|---|---|
| 正常 | 200 | `{accepted, rejected, filtered}` |
| batch > 100 事件 | 422 | pydantic validation error |
| 后端 record 异常（prom 内部错） | 200 | `{accepted, rejected+1, filtered}`（不抛 500） |
| 鉴权 | 401 | (限流中间件保护) |

## 6. 监控仪表盘推荐 PromQL

```promql
# 抽屉打开率（按来源分）
sum by (source) (rate(frontend_event_total{event="drawer_open"}[5m]))

# 错误边界触发频率（按 section）
sum by (source) (rate(frontend_event_total{event="error_boundary"}[5m]))

# SSE 解析错频率（按来源）
sum by (source) (rate(frontend_event_total{event="sse_parse_error"}[5m]))

# telemetry 接收成功率
sum(rate(telemetry_received_total{status="accepted"}[5m]))
  / sum(rate(telemetry_received_total[5m]))

# API 错误率（按路径）
sum by (path) (rate(api_request_total{status=~"5.."}[5m]))
  / sum by (path) (rate(api_request_total[5m]))

# 前端队列堆积（瞬时）
telemetry_queue_size > 50
```

## 7. 验收 checklist

- [x] 12 个事件全部双向白名单
- [x] 5 个 props 字段全白名单
- [x] PII regex 黑名单覆盖 email/中国手机/国际电话
- [x] 客户端 throttle 500ms + queue 200 + 批量 20/5s
- [x] sendBeacon pagehide 卸载 flush
- [x] 后端 3 counter + 1 gauge
- [x] /metrics 返 prom 文本格式（非 JSON）
- [x] 9/9 单元测试 + 6/6 E2E + 8/8 T7 E2E
- [x] health-check 9/0
