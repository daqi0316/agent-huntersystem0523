# 客户 Onboarding Runbook (P5-15)

更新时间: 2026-06-06
适用: AI Recruitment B2B 客户首个 30 天

## 1. 30 天 Onboarding 清单

| 天 | 任务 | 责任 | 验证 |
|---|---|---|---|
| D1 | 注册 + 培训 (30 min 视频会议) | 客户成功 | 客户加入培训群 + 收到账号 |
| D2-D3 | 数据导入 (候选人/职位) | 客户 (自助) 或 我们 (协助) | 导入 100+ 条 |
| D7 | 第一次完整跑通: 简历上传 → AI 评估 → 推送给 HR | 客户 | 至少 1 份评估产出 |
| D14 | 检查健康度: 7d 日活 ≥ 50%, 核心功能触发 ≥ 5 次 | 客户成功 | `/onboarding/health-score` |
| D21 | 微调: 反馈问题收集, prompt 优化 | 客户 + 我们 | 工单 ≤ 3 |
| D30 | 复盘: 续费决策 / 升级 plan / 退出风险评估 | 客户成功 | 周报推送 |

## 2. 数据导入 (D2-D3)

### 2.1 候选人导入
CSV 格式 (Excel 可直开):
```csv
name,email,phone,location,source
张三,zhang@x.com,13800138000,北京,linkedin
李四,li@x.com,,上海,referral
```

必填: `name`, `email`
可选: `phone`, `location`, `source` (默认 `csv_import`)

### 2.2 职位导入
```csv
title,department,location,description,requirements
高级 Python 工程师,工程,北京,负责核心服务,5 年 Python 经验
```

必填: `title`
可选: `department`, `location`, `description`, `requirements`

### 2.3 API 端点
- `GET /onboarding/csv-template/{entity_type}` — 拿模板
- `POST /onboarding/import/candidates` (multipart) — 上传
- `POST /onboarding/import/jobs` (multipart) — 上传
- `GET /onboarding/import/{batch_id}` — 查进度

## 3. 健康度评分 (D7, D14, D21, D30)

### 3.1 4 维度算法

| 维度 | 权重 | 公式 |
|---|---|---|
| 登录频次 | 40% | 过去 7d 活跃用户数 / 总用户数 × 100 × 1.5 (cap 100) |
| 功能使用 | 30% | 过去 7d 该 org 的 audit_log 条数 × 2 (cap 100) |
| 工单数 | 20% | 固定 80 (预留: 接客服系统后, 工单越多分越低) |
| 推荐行为 | 10% | 过去 30d 邀请数 × 20 (cap 100, max 5 invites) |

### 3.2 阈值

| 总分 | 风险等级 |
|---|---|
| 0-49 | 🔴 high_risk (高风险) |
| 50-69 | 🟡 at_risk (需关注) |
| 70-100 | 🟢 healthy (健康) |
| < 0 or > 100 | unknown (异常) |

### 3.3 API
- `GET /onboarding/health-score` — 查自己 (auto-compute if not exist)
- `POST /onboarding/health-score/refresh` — 重算
- `GET /onboarding/health-scores/all` — 管理员看所有客户 (按 total_score 升序, 高风险在前)

## 4. 周报推送 (D14 起)

### 4.1 触发
- cron: `0 9 * * 1` (每周一 09:00)
- 脚本: `scripts/weekly-health-report.py`
- 输出: 飞书 webhook (FEISHU_WEBHOOK_URL)

### 4.2 周报格式
```
📊 客户健康度周报 (每周一推送)

🔴 高风险 (< 50) (3 个)
  • org-abc123... 评分 32.5
  • org-def456... 评分 41.0
  ...

🟡 需关注 (50-70) (2 个)
  ...

🟢 健康 (≥ 70) (8 个)
  ...

📈 整体均值: 68.3
📊 总客户数: 13
```

### 4.3 挂载
```cron
# /etc/crontab
0 9 * * 1 cd /opt/ai-recruitment && /usr/bin/python3 apps/api/scripts/weekly-health-report.py >> /var/log/weekly-report.log 2>&1
```

## 5. 首次登录自动跟进

D1 培训结束后, 系统自动:
- 24h 后: 飞书提醒客户成功 "客户 X 已注册, 帮看一眼"
- 48h 后: 若用户没导入数据, 推 onboarding runbook 文档
- 7d 后: 若 `/onboarding/health-score.total < 30`, 飞书 P1 升级客户成功

## 6. 工单集成 (D21+)

预留 hook: 客户在系统内点 "需要帮助" → 飞书群 @ 客户成功
工单数接入 health_score.support_score 后:
- 0 工单/7d → 100 分
- 1-2 → 80 分
- 3-5 → 50 分
- > 5 → 20 分

## 7. 续费决策 (D30)

- 健康度 ≥ 70 → 自动续费
- 健康度 50-69 → 客户成功人工 contact, 推 1-on-1 培训
- 健康度 < 50 → 客户成功 + PM 一起 call, 调研流失原因

## 8. 异常情况

| 情况 | 处理 |
|---|---|
| CSV 编码非 UTF-8 | 自动 fallback 到 GBK (中文 Excel 默认) |
| 必填列缺失 | 该行跳过, errors[] 返回 row + 错误 |
| 邮箱重复 | 该行跳过 (数据库 unique 约束) |
| 1 万行 CSV | 同步处理 ~30s, 超时改异步 (Phase 6+) |

## 9. 与其他 Phase 集成

- P5-7 监控告警: 健康度 < 30 自动飞书 P1 告警
- P5-8 配额: 低健康度客户优先 LLM 配额告警
- P5-11 反垃圾: 大量邀请 (健康度低) → 风控升级
- P5-1 审计: onboarding 关键动作 (import / health refresh) 落 audit
