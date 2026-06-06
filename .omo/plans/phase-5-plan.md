# Phase 5 增长 + 转化 (月 3-4) — 详细规划

更新时间: 2026-06-06
时间窗: 2026-07 ~ 2026-08
北极星: 10 付费客户 + MRR ¥15K + 周活 > 60%
估时: 45d ≈ 9 周 (1 full-stack + 1 PM/运营)

## 0. Phase 4 已 ship 复用

| 资产 | 复用方式 |
|---|---|
| P5-15 健康度评分 (40/30/20/10 权重) | D7/D14/D21/D30 自动检测 + 飞书周报 |
| P5-11 邀请防刷 (同 IP 24h ≤ 3) | P6-4 老带新 共享限流 key |
| P5-7 监控告警 (5 规则) | P6-12 CSM churn 触发 |
| P5-3 支付 (微信 + 支付宝) | P6-3 自助注册 + P6-11 退款 复用 |
| P5-1 多租户 | 所有 Phase 5 模块默认 org-scoped |
| P5-8 灰度 (rollout_pct 0-100) | P6-7 A/B 测试 复用 |
| auth-context (微信扫码 + 邮箱) | P6-3 self-serve 复用 |

## 1. 13 任务详细规划 (P6-1 ~ P6-13)

按"客户增长漏斗"排序: 获客 → 转化 → 留存 → 飞轮 → 合规

### 🔴 Week 1-2 (07-01 ~ 07-12): 获客 (P6-1, P6-2, P6-3)

#### P6-1 Marketing 站 (8d)
**目标**: 百度收录 50+ 页, 知乎关注 +500

| 天 | 任务 | 验收 |
|---|---|---|
| D1-D2 | 站架构 (Next.js SSG + 国内 CDN): /, /pricing, /case-studies, /blog | Vercel/腾讯云 EdgeOne 部署 |
| D3-D4 | SEO meta: 5 模板 (title/description/og:url/image) + sitemap.xml + robots.txt + 中文 schema.org | Lighthouse SEO ≥ 95 |
| D5 | 内容页骨架: /blog/[slug] + MDX 支持 + 代码高亮 + 阅读时间 + 目录 | 1 篇模板文章上线 |
| D6-D7 | 案例页: /case-studies/[id] (3 个真实客户脱敏案例) + 数据可视化 (效率提升 X%) | 3 篇深度 case |
| D8 | 知乎引流 hook: 5 个问答 (招聘系统/AI 简历/HR 工具对比) 引导回官网 | 知乎 API 接入 + 定时发布 |

代码位置: `apps/web/app/(marketing)/` (route group, 不走 dashboard 布局)

#### P6-2 Onboarding 流 (3d)
**目标**: 注册 → 引导 → 第一个候选人 5 分钟内, 完成率 > 70%

| 天 | 任务 |
|---|---|
| D1 | 3 步引导 (welcome → 上传简历 → AI 评估) + 进度条 + 跳过选项 |
| D2 | 上下文提示 (D+1/D+3/D+7/D+14 触发, 见 P6-5) |
| D3 | 进度查询 + 鼓励首次评估 (gamification: "再上传 1 份解锁 AI 推荐") |

代码: `apps/web/app/(onboarding)/` (中间步骤不持久化到 org)

#### P6-3 Self-serve signup (2d)
**目标**: 无人工介入即可试用 14 天

| 天 | 任务 |
|---|---|
| D1 | 注册流: 手机号 + 微信扫码 (P5-2 复用) + 14 天试用 (subscription.status=trial) |
| D2 | 试用到期前 3 天飞书/短信提醒 (P6-5 集成) + 阻止登录引导付费 |

代码: 复用 P5-2 + P5-3 端点, 加 `subscription.trial_end_at` 字段

### 🟡 Week 3-4 (07-15 ~ 07-26): 转化 (P6-4, P6-5, P6-6)

#### P6-4 产品内 growth loop (2d)
**目标**: 邀请同事奖励 (seat +1), 邀请转化率 > 20%

| 天 | 任务 |
|---|---|
| D1 | referral_code 表 (org_id, code, created_by, uses, max_uses) + /invite/team endpoint |
| D2 | 接受流程: 验证 code → 注册 (走 P5-2 邀请 accept) → 双方 seat +1 奖励 (subscription 限额 +1) |

复用: P5-11 邀请防刷 (同 IP/device 限频) + P5-2 邀请 accept

#### P6-5 触达自动化 (4d)
**目标**: 站内信 + 微信模板消息 + 短信 (D+1/D+3/D+7/D+14)

| 天 | 任务 |
|---|---|
| D1 | 站内信表 (notification: id, user_id, type, title, body, read_at, created_at) + 列表/未读/已读 endpoint |
| D2 | 微信服务号模板消息 (微信公众号: 申请 + 模板审核 + 推送) |
| D3 | 短信触发器 (D+1 上传简历 / D+3 首次评估 / D+7 健康度低 / D+14 试用到期) |
| D4 | 飞书 webhook 备份通道 (微信失败时降级) |

代码: `apps/api/app/services/notification.py` + `apps/api/app/api/notifications.py`

#### P6-6 客户支持 (2d)
**目标**: 首响 < 4h, 站内 chat (美洽/智齿) + 知识库 + 工单

| 天 | 任务 |
|---|---|
| D1 | 知识库: 10 篇 FAQ (markdown) + /help 页面 + 搜索 |
| D2 | 工单集成: 美洽 (或智齿) 嵌入 chat widget + 客户-支持消息桥接 |

代码: `apps/web/app/(dashboard)/help/page.tsx` + 美洽 JS SDK 嵌入

### 🟢 Week 5-6 (07-29 ~ 08-09): 飞轮 (P6-7, P6-8, P6-9)

#### P6-7 A/B 测试框架 (3d)
**目标**: 定价页/CTA/注册流, 至少 1 个 A/B 上线, 有结论

| 天 | 任务 |
|---|---|
| D1 | experiments 表 (id, name, variants JSON, status, started_at) + 分配哈希 (user_id 决定 bucket) |
| D2 | analytics 集成 (埋点 impression/conversion) + 飞书周报 (A/B 转化率差异 + 显著性) |
| D3 | 第一个实验: 注册页 CTA 文案 (A: 免费试用 14 天 / B: 立即开始 AI 评估) |

代码: `apps/api/app/services/experiment.py` + `apps/web/lib/experiment.ts` + P5-8 灰度共享

#### P6-8 国内集成市场 MVP (10d)
**目标**: 至少 3 个集成, OAuth 接通

| 天 | 任务 |
|---|---|
| D1-D2 | 集成市场 UI: /integrations (钉钉/飞书/企业微信/WPS/腾讯文档 卡片列表 + 安装/卸载) |
| D3-D5 | 钉钉 OAuth 2.0 (国内 HR 渗透率最高) — 企业内应用 + corpsecret + 通讯录同步 |
| D6-D7 | 飞书 OAuth + 事件订阅 (面试通知/审批 推飞书) |
| D8-D10 | 企业微信 OAuth + 通讯录 + 应用消息 |

代码: `apps/api/app/services/integrations/{dingtalk,feishu,wecom}.py` + `apps/api/app/api/integrations.py`

#### P6-9 数据看板 (内部) (2d)
**目标**: CAC / LTV / Churn / NPS 周报 (企业微信机器人)

| 天 | 任务 |
|---|---|
| D1 | SQL 聚合视图: cac_by_channel / ltv_by_plan / churn_30d / nps_score |
| D2 | 周报 cron (企业微信 webhook, P5-15 周报同一脚本扩展) |

代码: `apps/api/scripts/growth-weekly-report.py` + `docs/internal-dashboard.md`

### ⚪ Week 7-8 (08-12 ~ 08-23): 留存 (P6-10, P6-11, P6-12)

#### P6-10 案例研究 (2d)
**目标**: 1 个深度 case, 放官网

| 天 | 任务 |
|---|---|
| D1 | 第 1 个付费客户的 before/after 数据 (P6-9 看板) + 视频采访 30min |
| D2 | /case-studies/[id] 页面 + B 站/视频号分发 + 知乎回答引用 |

#### P6-11 退款/争议流程 (1d)
**目标**: 微信支付/支付宝 dispute 处理 SOP

| 天 | 任务 |
|---|---|
| D1 | 客服 SOP 文档 + 退款接口 (复用 P5-3 退款 API) + 飞书群通知 (争议 case) |

#### P6-12 CSM 主动 churn 监控 (2d)
**目标**: 7 天未登录自动飞书通知 CSM

| 天 | 任务 |
|---|---|
| D1 | daily cron 检查 last_login_at > 7d → 飞书 CSM 群 + 客户成功 @ (P5-7 alert 升级) |
| D2 | health score < 30 时 P1 升级, CSM 自动收到 1-on-1 任务 (P5-15 健康度) |

代码: `scripts/csm-churn-monitor.py` (cron daily)

### ⚫ Week 9 (08-26 ~ 08-30): 合规 (P6-13)

#### P6-13 可访问性 WCAG 2.2 AA (4d)
**目标**: 自动化 a11y 测试 + 关键页面 100% 通过

| 天 | 任务 |
|---|---|
| D1 | 集成 axe-core + jest-axe, 跑现有组件, 记录 violations |
| D2 | 修复: 颜色对比度 / aria-label / 键盘导航 / 焦点环 |
| D3 | 修复: 表单错误 / 屏幕阅读器 / 跳转链接 / 标题层级 |
| D4 | CI 接入 (axe-core fail = 拒绝 merge) + 关键页 100% |

代码: `apps/web/tests/a11y/` + `.github/workflows/a11y.yml`

## 2. 14 任务优先级 (MUST/SHOULD/COULD)

| 优先级 | 任务 | 阻塞 |
|---|---|---|
| MUST | P6-3 (self-serve signup) | 无, 立即可做 |
| MUST | P6-5 (触达自动化) | 微信公众号申请 (1 周) + 阿里云短信 (已有) |
| MUST | P6-9 (数据看板) | 无, 内部用 |
| SHOULD | P6-4 (产品内 growth loop) | 无, 复用 P5-2 + P5-11 |
| SHOULD | P6-7 (A/B 测试) | 无, 复用 P5-8 灰度 |
| SHOULD | P6-12 (CSM churn 监控) | 无, 复用 P5-15 健康度 |
| SHOULD | P6-2 (onboarding 流) | 无 |
| SHOULD | P6-13 (WCAG) | 无, 合规需要 |
| COULD | P6-1 (marketing 站) | 百度收录需时间 (1-3 月自然增长) |
| COULD | P6-6 (客户支持) | 美洽/智齿 商务对接 (1-2 周) |
| COULD | P6-8 (集成市场) | 钉钉/飞书/企微 OAuth 申请 (1-2 周/平台) |
| COULD | P6-10 (案例研究) | 需客户同意 + 视频采访 |
| COULD | P6-11 (退款流程) | P5-3 已 ship, 仅 SOP 文档 |

## 3. 5 大架构决策

| # | 决策 | 影响 |
|---|---|---|
| 1 | **国内 only / 无邮件** | 站内信 + 微信模板 + 短信 触达组合 (3 渠道冗余) |
| 2 | **A/B + 灰度 复用 P5-8 rollout** | 灰度 P0 + 实验 P1, 同一套 sliding window |
| 3 | **健康度 + churn 双指标监控** | 健康度 < 30 (P1) + 7d 未登录 (P2) CSM 自动响应 |
| 4 | **集成市场先钉钉** | 国内 HR 渗透率最高 (70%+), 飞书/企微 二期 |
| 5 | **Marketing 站 + 仪表台站分离** | 营销站 SSG/SEO, 仪表台 SPA/auth, 共享组件库 |

## 4. 风险登记册 (Top 5)

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 自助注册后无引导 → 流失 | 高 | 高 | P6-2 onboarding + P6-5 D+1/D+3/D+7/D+14 触达 |
| 微信公众号模板审核被拒 | 中 | 中 | 站内信兜底 + 短信备份通道 |
| 钉钉/飞书 OAuth 申请延期 | 中 | 中 | 先上工单集成 (P6-6 美洽), 集成市场 P6-8 二期 |
| 客户白鼠 30 天未达成 10 单 | 中 | 高 | 1-on-1 主动 call, 调整 onboarding runbook |
| 微信支付/支付宝 dispute 投诉 | 低 | 中 | P6-11 SOP + 飞书群 CSM 实时响应 |

## 5. 资源日历

| 资源 | 截止 | 责任 |
|---|---|---|
| 微信公众号服务号 (P6-5) | 06-15 申请 | 你 |
| 微信模板消息模板 ID (P6-5) | 06-25 审核 | 你 |
| 钉钉/飞书/企微 OAuth 申请 (P6-8) | 06-20 | 你 |
| 美洽/智齿 商务对接 (P6-6) | 06-30 | 你 |
| 1-2 个付费 B2B 客户白鼠 | 06-15 启动 | 你 |
| Marketing 站 域名 (airecruit.com) | 06-20 | 你 |

## 6. 紧急升级路径 (沿用 P4)

| 时间 | 事故 | 升级到 |
|---|---|---|
| 工作日 09-18 | P0/P1 | 我 (full-stack) → 你 (PM, 5min) |
| 夜间 / 周末 | P0 | 我 (on-call 7×24) → 你 (飞书 5min) |
| 30min 无响应 | 阿里云工单 + 客户群公告 | — |

## 7. KPI 验收 (Phase 5 完成的硬指标)

| 维度 | 目标 | 验证 |
|---|---|---|
| 获客 | 10 付费客户 (8 SMB + 2 中型) | 后台 admin /customers |
| 转化 | CAC < ¥500 | P6-9 看板 |
| 留存 | 周活 > 60% (DAU/WAU) | P5-7 埋点 + 看板 |
| 口碑 | 老带新转化 > 20% | P6-4 invitation accept 率 |
| 触达 | 微信模板 + 短信 95% 送达 | P6-5 webhook 监控 |
| 合规 | WCAG 2.2 AA 100% | axe-core 自动化 |
| NPS | > 30 (首批客户调研) | 季度问卷 |
| 集成 | 至少 3 个 (钉钉/飞书/企微) | P6-8 后台 |
| 文档 | 4 份 (marketing/onboarding/growth-runbook/ab-results) | — |
| 测试 | 新增 ≥ 50 个 (P6-4/5/7/12) | pytest 0 fail |

## 8. 排期 (4 周可见 + 4 周缓冲 + 1 周收尾)

W1 (07-01 ~ 07-05): P6-3 self-serve + P6-9 数据看板 (2 个 0 阻塞)
W2 (07-08 ~ 07-12): P6-4 growth loop + P6-7 A/B (2 个 0 阻塞)
W3 (07-15 ~ 07-19): P6-2 onboarding + P6-12 CSM churn (2 个)
W4 (07-22 ~ 07-26): P6-1 marketing 站 (基础 + SEO)
W5 (07-29 ~ 08-02): P6-5 触达自动化 (4d, 等微信模板审核)
W6 (08-05 ~ 08-09): P6-8 集成市场 钉钉 (5d)
W7 (08-12 ~ 08-16): P6-10 案例 + P6-11 退款 SOP
W8 (08-19 ~ 08-23): P6-13 WCAG (4d) + P6-6 客户支持
W9 (08-26 ~ 08-30): 收尾 + 1-2 客户白鼠 30 天验证

每日节奏: 09:00 standup (5min) + 18:00 日报 (我做, 你看)

## 9. 不在 Phase 5 范围

- 海外市场 / 出海 (Phase 7+ 再议)
- 邮件营销 (站内信 + 微信 + 短信 替代)
- 钉钉/飞书/企微 通讯录深度集成 (Phase 6)
- 视频面试 (Phase 6+ AI 能力)
- 私有化部署 (Phase 8 enterprise 触发)
- 等保三级 (Phase 7 启动)
- 种子轮融资 (Phase 7 启动)
