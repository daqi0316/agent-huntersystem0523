# 监控告警 Runbook (P5-7)

更新时间: 2026-06-06
适用: AI Recruitment 生产 + staging

## 1. 指标端点

- `/metrics` (Prometheus 文本格式) — 8 类指标
- `/health` (200/ok) — 存活探针
- Sentry (后端) — `SENTRY_DSN` 设了才生效, 否则跳过

## 2. 8 类指标

| 指标 | 类型 | 用途 |
|---|---|---|
| `frontend_event_total` | Counter | 前端事件埋点 (T6) |
| `api_request_total` | Counter | API 请求 (method/path/status) |
| `http_request_duration_seconds` | Histogram | HTTP 延迟, p99 告警用 |
| `http_5xx_total` | Counter | 5xx 错误, 错误率告警用 |
| `db_pool_used` / `db_pool_size` | Gauge | DB 连接池, 80% 告警用 |
| `llm_request_total` / `llm_token_total` | Counter | LLM 用量, 配额告警用 |
| `llm_failure_total` | Counter | LLM 失败, 5% 告警用 |
| `llm_token_quota_remaining` | Gauge | 配额剩余, 20% 预警用 |

## 3. 5 条告警规则

| 规则 | 阈值 | 窗口 | 严重度 | 升级 |
|---|---|---|---|---|
| http_5xx_rate_high | > 0.5% | 1min | P1 | 5min→PM, 30min→工单 |
| http_p99_latency_high | > 2s | 1min | P1 | 同上 |
| db_pool_high | > 80% | 1min | P1 | 同上 |
| llm_failure_rate_high | > 5% | 5min | P1 | 同上 |
| llm_token_quota_low | < 20% | 1d | P2 | 仅首次通知 |

## 4. 升级路径 (P0 事故响应)

```
告警触发
  ↓
[0-5min]  飞书 webhook 通知 PM
  ↓ ack (手动)
[5min+]   飞书 @ PM 升级
  ↓ ack
[30min+]  阿里云工单 (P1) + 客户群公告 (P0)
  ↓
[P0 支付/数据] 银行暂停商户号 (24h)
```

ack 机制: `/var/lib/ai-recruitment/alert_acks.json` 文件持久化, `scripts/alert-escalation.py` cron 每 5min 跑。

## 5. 飞书 Webhook 配置

```bash
# 飞书群 → 设置 → 群机器人 → 自定义 webhook
FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
```

挂到 systemd timer 或 crontab:
```cron
*/5 * * * * cd /opt/ai-recruitment && /usr/bin/python3 apps/api/scripts/alert-escalation.py >> /var/log/alert-escalation.log 2>&1
```

## 6. Sentry 接入

后端:
```bash
SENTRY_DSN=https://xxx@sentry.io/123
SENTRY_ENV=production
GIT_SHA=$(git rev-parse --short HEAD)  # release tracking
SENTRY_TRACES_SAMPLE_RATE=0.1
```

前端 (.env.local):
```bash
NEXT_PUBLIC_SENTRY_DSN=https://xxx@sentry.io/123
NEXT_PUBLIC_SENTRY_ENV=production
NEXT_PUBLIC_GIT_SHA=$(git rev-parse --short HEAD)
```

PII 自动脱敏 (email/name/phone/password/wechat_unionid) 不上报。

## 7. Chaos 演练

```bash
# 演练全部 4 条主规则
bash scripts/chaos-drill.sh all

# 单独演练
bash scripts/chaos-drill.sh 5xx
bash scripts/chaos-drill.sh p99
bash scripts/chaos-drill.sh db
bash scripts/chaos-drill.sh llm
```

演练后检查:
1. 飞书群是否 5min 内收到 webhook
2. `/var/lib/ai-recruitment/alert_acks.json` 是否有新条目
3. Sentry 是否捕获异常 (chaos 期间应有)
4. `/metrics` 端点是否显示相关 metric 增量

## 8. 日常运维

### 8.1 看当前活跃告警
```bash
curl -sS http://localhost:8000/metrics | grep -E "(_5xx_total|_pool_used|_failure_total)" | head -20
```

### 8.2 重置 ack 状态
```bash
sudo rm /var/lib/ai-recruitment/alert_acks.json
```

### 8.3 加新告警规则
编辑 `app/core/telemetry.py` 的 `ALERT_RULES`, 加新 dict 即可, 改后:
```bash
make api:dev  # 重启进程, 重新加载模块
```

## 9. 故障排查清单 (按告警类型)

### 9.1 5xx 错误率高
1. 看 `apps/api/app.log` 最近 ERROR
2. Sentry 最近 issue
3. DB 连接数 (PG: `SELECT count(*) FROM pg_stat_activity`)
4. LLM 服务是否在跑 (omlx / vllm)
5. 最近是否刚部署 (回滚?)

### 9.2 p99 延迟高
1. 看 `db_pool_used` 是否满
2. 看 LLM 延迟 (P50/P99, omlx/vllm 日志)
3. Sentry trace 找慢请求
4. 最近是否加新 SQL (无索引?)

### 9.3 DB 连接池满
1. 看 `pg_stat_activity` 哪些 query 持锁
2. 业务流量是否突增
3. 长事务 (> 30s) 是否有

### 9.4 LLM 失败率高
1. omlx / vllm 进程是否在跑
2. 模型文件是否完整 (Qwen3.6-35B-A3B-4bit)
3. GPU 是否 OOM (nvidia-smi)
4. 网络是否通 (LLM_BASE_URL)

### 9.5 LLM 配额低
1. 飞书群预警
2. 通知 owner 是否续费 / 升级 plan
3. 超限后系统自动降级到便宜模型 (P5-8 ship 后)
