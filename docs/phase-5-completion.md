# Phase 5 增长 + 转化 — 收尾总结

更新时间: 2026-06-06
总体 ship: 10/13 任务 (P6-6 / P6-8 / P6-10 阻塞中, 等美洽 / 3 平台 OAuth / 1-2 客户白鼠)

## 1. 任务完成度

| ID | 任务 | 估时 | 实际 | Commit | 状态 |
|---|---|---|---|---|---|
| P5 规划 | Momus 审 + 详细规划 (6.5→8.5/10) | — | — | d17689c | ✅ |
| P6-3 | self-serve trial (14 天) | 2d | 1d | d262640 | ✅ |
| P6-4 | 老带新 (referral_code + 双方 seat+1) | 2d | 1d | d262640 | ✅ |
| P6-9 | 数据看板 (CAC/LTV/Churn/Referral) | 2d | 1d | d262640 | ✅ |
| P6-7 | A/B 框架 (分配哈希 + 显著性) | 3d | 1d | 2e925f6 | ✅ |
| P6-12 | CSM churn 监控 (7d + 健康度<30 + 试用到期) | 2d | 1d | 9feffde | ✅ |
| P6-2 | onboarding 流 (3 步) | 3d | 1d | 0810b9f | ✅ |
| P6-11 | 退款 SOP 文档 | 1d | 0.5d | 6fdb82e | ✅ |
| P6-13 | WCAG 2.2 AA 静态审计 (0 critical) | 4d | 0.5d | 6fdb82e | ✅ |
| P6-1 | marketing 站 (首页/价格/博客 + SEO) | 8d | 1d (partial) | d7d64f4 | ✅ (partial, 案例页 + 知乎 hook 等客户白鼠) |
| P6-5 D1 | in-app 触达 (12 通知 + D+1/3/7/14) | 4d | 0.5d | b1567ea | ✅ (0 阻塞部分) |
| P6-5 D2-D4 | 微信模板 + 短信 + 飞书 | 4d | 0d | — | ⏸ BLOCKED on 微信模板 + 飞书 |
| P6-6 | 客户支持 (美洽 widget) | 2d | 0d | — | ⏸ BLOCKED on 美洽商务 |
| P6-8 | 集成市场 (钉钉/飞书/企微) | 10d | 0d | — | ⏸ BLOCKED on 3 平台 OAuth |
| P6-10 | 案例研究 | 2d | 0d | — | ⏸ BLOCKED on 客户白鼠 |

**总计**: 10/13 任务 ship, 估时 31d, 实际 6.5d (mock/复用 + 0 阻塞快)

## 2. 测试统计 (Phase 5 增量)

| Test 文件 | 用例 | Pass |
|---|---|---|
| test_growth.py (P6-3 + P6-4) | 18 | 18 ✅ |
| test_dashboard_growth.py (P6-9) | 12 | 12 ✅ |
| test_experiment.py (P6-7) | 13 | 13 ✅ |
| test_csm.py (P6-12) | 9 | 9 ✅ |
| test_notification.py (P6-5) | 8 | 8 ✅ |
| **P5 新增小计** | **60** | **60 ✅ 0 退化** |
| P4 阶段 144 测试 | 143/144 | 1 env fail (已知) |

## 3. 复用 Phase 4 资产

| Phase 4 资产 | Phase 5 复用 |
|---|---|
| P5-1 多租户 (org_scoped_db) | 所有 10 endpoint 默认 org-scoped |
| P5-2 邀请 (accept + 邀请流) | P6-4 referral 复用 accept 端点 |
| P5-11 邀请防刷 (同 IP/device) | P6-4 复用同频次限制 |
| P5-15 健康度评分 (40/30/20/10) | P6-12 CSM 复用 + 触发 P1 任务 |
| P5-7 监控告警 (Prometheus + 飞书) | P6-12 飞书 webhook + P6-9 看板 |
| P5-8 3-key 限流 (org/user/IP) | P6-1 marketing 站 隐式防刷 |
| auth-context (微信扫码 + 邮箱) | P6-3 self-serve 复用 |

## 4. Phase 5 5 大架构决策

| # | 决策 | 影响 |
|---|---|---|
| 1 | **国内 only / 无邮件** | 站内信 + 微信模板 + 短信 3 通道冗余 (D+1/D+3/D+7/D+14) |
| 2 | **A/B 复用 P5-8 灰度** | rollout_pct 0-100 + md5 哈希稳定分配 + z-test 显著性 |
| 3 | **健康度 + churn 双指标 CSM 监控** | 自动 1-on-1 任务 + P1/P2 严重度 + 飞书通知 |
| 4 | **marketing 站 + 仪表台站分离** | `(marketing)` route group, 独立 layout/SEO/sitemap |
| 5 | **站内信优先 + 微信模板备份** | D+1 通知不依赖 微信模板审核 (审核周期长), 模板到位后无缝切换 |

## 5. 文档产出 (7 份 Phase 5 新增)

| 文档 | 用途 |
|---|---|
| .omo/plans/phase-5-plan.md | 13 任务详细规划 |
| .omo/plans/phase-5-momus-review.md | 10 P0 + 8 P1 修复记录 |
| docs/refund-dispute-sop.md | 退款 / 争议处理 SOP |
| docs/onboarding-runbook.md (P5-15) | 30 天 onboarding 清单 + 健康度 + 周报 |
| docs/monitoring-runbook.md (P5-7) | 5 告警 + 升级路径 |
| scripts/a11y-audit.py | WCAG 2.2 AA 静态审计 |
| scripts/csm-churn-monitor.py | 每日 CSM 任务生成 + 飞书 |

## 6. 关键运营 SOP

### 6.1 每日 CSM 监控 (cron 09:00)
```bash
python3 scripts/csm-churn-monitor.py
# 扫描: 7d 未登录 / 健康度 < 30 / 试用 3d 内到期
# 飞书通知 + 建 csm_task
```

### 6.2 每周健康度 + 增长周报 (cron 周一 09:00)
```bash
python3 scripts/weekly-health-report.py
# 客户健康度 (高/中/低风险分组) + 增长 (CAC/LTV/Churn/Referral)
```

### 6.3 onboarding D+1/D+3/D+7/D+14 站内信
```python
# app/services/notification.py ONBOARDING_TEMPLATES
# 4 个定时触发, 已接入 notification 表
```

## 7. 阻塞项 + 备案

| ID | 阻塞 | 备案 | 启动预估 |
|---|---|---|---|
| P6-5 D2 | 微信服务号 + 模板审核 | 站内信优先 + 模板到位后无缝切换 | 6-25 模板审核 |
| P6-5 D3 | 阿里云短信 (AccessKey) | 已有 P5-11 反垃圾短信代码, 加 trigger 即可 | 1d |
| P6-5 D4 | 飞书 webhook URL | 当前用 P5-7 告警 webhook, 共用同一机器人 | 1d |
| P6-6 | 美洽/智齿 商务对接 | 工单内部流转 (1d scaffold) | 6-30 签约 |
| P6-8 钉钉 | OAuth 申请 | 自建应用 + corpsecret (1 周审批) | 6-20 |
| P6-8 飞书 | OAuth 申请 | 飞书开放平台 (1 周审批) | 6-20 |
| P6-8 企微 | OAuth 申请 | 企业微信服务商 (1 周审批) | 6-20 |
| P6-10 | 1-2 客户白鼠 + 视频采访 | 第 1 个客户 7 月初跑通, 8 月初发布 | 7-01 |

## 8. 客户白鼠 启动 步骤 (待你)

1. **联系 1-2 个付费 B2B 客户** (6-15 启动)
2. **走 P6-2 onboarding 流** (welcome → upload → evaluate)
3. **试用 14 天内**: 引导 至少 1 个 JD + 3 个候选人 (P6-9 看板上能看)
4. **D+1/D+3/D+7/D+14 触达** 自动验证 (P6-5 in-app 通知)
5. **D+7/D+14/D+30 健康度** 监控 (P5-15)
6. **7d 未登录 → CSM P1 升级** (P6-12)
7. **D+11 (试用到期前 3 天) → 飞书 P2 提醒 + in-app D+14 通知** (P6-5 D3)
8. **D+30 续费决策**: 健康度 ≥ 70 续费, 50-70 主动 call, < 50 调研流失

## 9. Phase 5 KPI 验收 (30 天后)

| 维度 | 目标 | 验证 |
|---|---|---|
| 获客 | 10 付费客户 (8 SMB + 2 中型) | /growth/dashboard/summary |
| 转化 | CAC < ¥500 | P6-9 看板 |
| 留存 | 周活 > 60% (DAU/WAU) | P5-7 埋点 |
| 口碑 | 老带新转化 > 20% | P6-4 referral_uses / codes |
| 触达 | 微信模板 + 短信 95% 送达 | P6-5 webhook 监控 |
| 合规 | WCAG 2.2 AA 100% | scripts/a11y-audit.py |
| NPS | > 30 (首批客户) | 季度问卷 |
| 集成 | 至少 3 个 (钉钉/飞书/企微) | P6-8 (阻塞) |
| 文档 | 5 份 (marketing/onboarding/growth-runbook/ab-results) | — |
| 测试 | 新增 ≥ 50 (P6-4/5/7/12) | pytest 0 fail |

## 10. Phase 5 → Phase 6 衔接

- Phase 6 (规模化) 重点: 30 客户 → 多 region + AI 准确率提升 + 等保三级
- Phase 5 完成后 1-2 客户白鼠跑通, 验证 PMF 后启动 Phase 6 招聘 (AI 工程师 + 销售)
- 种子轮融资: Phase 6 启动 ¥1-3M

## 11. Phase 4 + Phase 5 累计 (2026-06 至今)

| 阶段 | Ship 任务 | Commits | 测试 | 文档 |
|---|---|---|---|---|
| Phase 4 (P5-1..P5-15) | 14/16 | 22 | 144 新 (143 pass + 1 env) | 14 份 |
| Phase 5 (P6-3..P6-13) | 10/13 | 8 | 60 新 (60 pass) | 7 份 |
| **总计 (今日)** | **24/29** | **30** | **204 新 (203 pass + 1 env)** | **21 份** |

---

**Phase 5 状态**: 10/13 ship, 0 阻塞部分 100% 交付。
**当前 0 阻塞可继续**: P6-6 客户支持 scaffold (工单内部流转, 美洽可后接) / P5-9 法务模板 (ToS/PP/DPA, 等律师后审)。
**需你启动**: 1-2 付费 B2B 客户白鼠 (06-15) → 走 P6-2 onboarding → 30 天验证 Phase 5 全部指标。
