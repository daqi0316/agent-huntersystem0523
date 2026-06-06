# Deployment Runbook

更新时间: 2026-06-06
版本: v1.0
适用: AI Recruitment 生产环境 (staging.airecruit.com, app.airecruit.com)

## 0. 架构总览

```
Internet
   │
   ▼
┌────────┐
│ Nginx  │ (443/80, SSL, reverse proxy, CSP headers)
│ :443   │
└────┬───┘
     │
     ├─► /api/*  → api:8000 (gunicorn + 4 uvicorn workers)
     │
     └─► /*      → web:3000 (Next.js standalone)

Backend services (internal network only):
  postgres:5432  (with pg_dump daily backup)
  redis:6379     (maxmemory 512MB, allkeys-lru)
  qdrant:6333    (vector store)
  minio:9000     (file storage, S3-compatible)
```

## 1. 初次部署 (staging)

### 1.1 前置
- [ ] 阿里云 ACK 集群已创建 (2 CPU / 4GB / 1 节点, staging)
- [ ] 域名 staging.airecruit.com 解析到 LB
- [ ] SSL 证书 (Let's Encrypt) 已申请, 路径 `docker-assets/ssl/fullchain.pem` + `privkey.pem`
- [ ] .env.prod 已填, 见 §1.3

### 1.2 一键部署
```bash
cd /opt/ai-recruitment
git clone git@github.com:your-org/your-repo.git .
cp .env.prod.example .env.prod
# 编辑 .env.prod 填入真值
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
curl -fsS https://staging.airecruit.com/health
```

### 1.3 .env.prod 模板
```bash
POSTGRES_USER=airecruit_app
POSTGRES_PASSWORD=<from KMS>
POSTGRES_DB=ai_recruitment
MINIO_ROOT_USER=airecruit
MINIO_ROOT_PASSWORD=<from KMS>
CORS_ORIGINS='["https://staging.airecruit.com"]'
NEXT_PUBLIC_API_URL=https://staging.airecruit.com
NEXT_PUBLIC_WS_URL=wss://staging.airecruit.com
WECHAT_MOCK_MODE=true
LLM_BASE_URL=http://host.docker.internal:8000/v1
LLM_PROVIDER=omlx
```

## 2. 日常运维

### 2.1 健康检查
```bash
# 一键
bash scripts/health-check.sh
# 期望: 7/7 pass (含 Step 7 微信登录)

# 单独检查
curl -fsS https://staging.airecruit.com/health
docker compose -f docker-compose.prod.yml ps
```

### 2.2 查看日志
```bash
# 单服务
docker compose -f docker-compose.prod.yml logs -f api --tail=100
docker compose -f docker-compose.prod.yml logs -f web --tail=100
docker compose -f docker-compose.prod.yml logs -f nginx --tail=100

# 全服务时间窗
docker compose -f docker-compose.prod.yml logs --since="2026-06-06T00:00:00" --until="2026-06-06T01:00:00"
```

### 2.3 重启服务
```bash
# 单服务
docker compose -f docker-compose.prod.yml restart api

# 滚动重启 (零停机)
docker compose -f docker-compose.prod.yml up -d --no-deps api
```

### 2.4 数据库迁移
```bash
# 升级
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# 降级 (回滚 1 步)
docker compose -f docker-compose.prod.yml run --rm api alembic downgrade -1

# 看历史
docker compose -f docker-compose.prod.yml run --rm api alembic history
```

### 2.5 备份
```bash
# 手动触发 (脚本默认 daily cron)
bash scripts/backup-postgres.sh

# 恢复
gunzip -c /backup/postgres/ai_recruitment_20260606_030000.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T postgres psql -U airecruit_app -d ai_recruitment
```

### 2.6 备份保留策略
- 每日: 7 天 (本地)
- 每周日: 4 周 (本地)
- 每月 1 号: 12 月 (本地 + OSS)
- RPO: 1h (daily 03:00 backup)
- RTO: 30min (从本地 + 验证 + 切流量)

## 3. 5 分钟回滚 SOP (P0-13)

### 触发条件
- 部署后 5min 内健康检查失败
- 错误率 5xx > 5% (1min 滑窗)
- 关键功能不可用 (登录/支付/邀请)

### 步骤
```bash
# 1. SSH 到生产 (1min)
ssh prod-user@prod-host

# 2. 触发回滚 (1min)
cd /opt/ai-recruitment
bash scripts/rollback.sh

# 3. 验证 (2min)
bash scripts/health-check.sh
# 期望: 7/7 pass
```

### 失败 fallback
- 脚本失败 → 手动:
  ```bash
  cd /opt/ai-recruitment
  PREVIOUS=$(cat .previous_tag)
  API_IMAGE_TAG=$PREVIOUS WEB_IMAGE_TAG=$PREVIOUS \
    docker compose -f docker-compose.prod.yml up -d --no-deps api web
  ```
- 仍失败 → 飞书告警 + 阿里云工单 (P1) + 客户群公告 (P0)

## 4. 紧急升级路径

| 时间 | P0 事故 | 升级到 |
|---|---|---|
| 工作日 09-18 | 我 (full-stack) | 你 (PM, 5min) |
| 夜间 / 周末 | 我 (on-call 7×24) | 你 (PM, 飞书 5min) |
| 我俩 30min 无响应 | 阿里云工单 (P1+) | 客户群公告 (P0) |

飞书 webhook: 见 §6

## 5. 监控指标 + 告警规则

详见 docs/monitoring-runbook.md (P5-7 ship 后)

## 6. 凭据 (阿里云 KMS + 飞书 Webhook)

| 凭据 | 位置 | 备注 |
|---|---|---|
| POSTGRES_PASSWORD | 阿里云 KMS `prod/db/password` | 仅 prod cluster 拉取 |
| MINIO_ROOT_PASSWORD | 阿里云 KMS `prod/minio/password` | 同上 |
| JWT_SECRET | 阿里云 KMS `prod/jwt/secret` | ≥32 字符 |
| WECHAT_CORP_SECRET | 阿里云 KMS `prod/wechat/secret` | 切真模式时用 |
| 飞书 webhook | 飞书群机器人 token | 监控告警 + 部署通知 |

## 7. 常见问题 (FAQ)

### Q1: API 容器反复重启
A: `docker compose logs api --tail=50` 看 stderr
   常见: DATABASE_URL 拼错 / JWT_SECRET 太短 / LLM_BASE_URL 不可达

### Q2: 健康检查 200 但用户报 502
A: 99% 是 nginx upstream 连不上
   `docker compose exec nginx curl -fsS http://api:8000/health` 验证内部网络
   `docker compose exec nginx curl -fsS http://web:3000/` 验证 web

### Q3: 数据库连接数爆
A: `docker compose exec postgres psql -U airecruit_app -c "SELECT count(*) FROM pg_stat_activity"`
   调整: docker-assets/postgres-tuning.conf + 重启 postgres

### Q4: 备份失败
A: `bash scripts/backup-postgres.sh 2>&1 | tail -20`
   常见: 磁盘满 (df -h) / PGPASSWORD 未设 / postgres 容器挂了

## 8. 升级 checklist

每次升级前:
- [ ] 备份已跑 (`ls -lat /backup/postgres/ | head -1`)
- [ ] staging 已验证 24h
- [ ] 通知客户 (如 breaking change)
- [ ] 飞书群在场, 监控告警 ready
- [ ] 回滚 SOP 已知会 on-call

升级中:
- [ ] CI/CD 触发 (main 合并)
- [ ] 健康检查 7/7
- [ ] 监控 5min 内无异常
- [ ] 客户群状态良好

升级后:
- [ ] 1h 后回看监控
- [ ] 24h 后回看监控 + 客户反馈
- [ ] 7d 后写升级报告 (commits + 风险 + 教训)
