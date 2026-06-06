# Phase 4 商用化 — Momus 审核 + 详细规划

更新时间: 2026-06-06
审核者: Momus (Plan Critic)
初版评分: **6.0/10** (有 P0 漏洞, 不可直接执行)
修订后评分: **8.5/10** (本文件 Part 2 已修复 P0 + 关键 P1)

---

## Part 1: Momus 审核报告

### 1.1 总体评分

| 维度 | 评分 | 说明 |
|---|---|---|
| **清晰度** | 6/10 | "D1 D2 D3" 排期与"完成定义"混淆, "跑通" 含义模糊 |
| **可验证性** | 4/10 | 每个 task 无 DoD, 无反向 case, 无验收硬指标 |
| **完整性** | 5/10 | 缺依赖图/风险册/假设清单/紧急升级路径 |
| **估算现实性** | 6/10 | 估时基于"1 full-stack + 1 PM 完美并行", 实际 80% 串行 |
| **风险覆盖** | 5/10 | 顶级风险没量化 (退款/对账/数据删除外键/告警风暴) |

**综合**: 6.0/10 — **不可直接 dispatch, 需补 P0 + 关键 P1 后才能执行**

### 1.2 P0 关键问题 (必须修, 否则 5 周内必有事故)

| ID | 问题 | 位置 | 风险 |
|---|---|---|---|
| P0-1 | 支付**无对账 + 无退款 + 状态机不闭环** | P5-3 | 客户付 ¥3000 收不到/重复扣款/退款后状态卡死 → 投诉+法务+丢客户 |
| P0-2 | 个保法**删除破坏外键** (user_id 引用 5+ 表) | P5-4 | 软删后其他表的 user_id 仍指向已"删除" user, 数据不一致 + 后续硬删 cascade 误伤其他用户 |
| P0-3 | 个保法**宽限期用户能否登录没说** | P5-4 | 删除中用户可继续操作 → 违反 Art. 17 (撤回权) |
| P0-4 | 部署**缺 CI/CD + 日志 + secrets + 备份恢复** | P5-6 | 部署后出问题, 找不到日志, 回滚不了 DB, secrets 在代码里 |
| P0-5 | 监控**告警阈值未量化** ("5xx > 1%" 怎么算? per 分钟? per 小时?) | P5-7 | 告警要么永远不响, 要么天天响, oncall 疲劳 |
| P0-6 | 监控**无告警升级路径** (P1 → P2 → 老板) | P5-7 | 凌晨 3 点 P0 告警只发给 1 人, 他没看就 SLA 破 |
| P0-7 | 配额**限流 key 不明** (org_id? user_id? IP?) | P5-8 | 误限导致客户 429 风暴投诉, 或漏限被恶意刷 |
| P0-8 | **无跨 task 依赖图** | 全局 | W1 卡住一个 task, 不知道 W2/W3 哪些能提前/哪些要延期 |
| P0-9 | **无风险登记册** (top 5 风险 + 缓解 + Owner + 触发) | 全局 | 风险临时想起来, 没预案 |
| P0-10 | **无 KPI/DoD** (Phase 4 完成 = ?) | 全局 | 4 周后没法判断"做完了没", 客户/老板问"还要多久"答不上 |
| P0-11 | **无紧急升级路径** (凌晨出事找谁?) | 全局 | P0 事故无 owner, 互相等 |
| P0-12 | **无假设清单** (汇率/法规/律师/凭据到位) | 全局 | 假设破 = 整个 plan 延期, 没备案 |

### 1.3 P1 重要问题 (1 周内应修)

| ID | 问题 | 位置 |
|---|---|---|
| P1-1 | 法务**律师时间窗 + 付费机制没说** | P5-9 |
| P1-2 | AI 监管**来源标识格式 + UI 位置 + 申诉 SLA 未定义** | P5-10 |
| P1-3 | 反垃圾**手机号 vs email 注册策略不一致** | P5-11 |
| P1-4 | 估时**默认双方完美并行, 实际 80% 串行** (我等你凭据) | 全局 |
| P1-5 | 支付**未提不同 plan 的升级/降级状态机** (从 starter 升 pro, 中间怎么处理?) | P5-3 |
| P1-6 | 监控**未提 LLM token 用量告警** (P5-8 quota 相关, 应一并做) | P5-7 + P5-8 |
| P1-7 | **回滚 SOP 5 分钟没测过, 包括 DB migration downgrade** | P5-13 |
| P1-8 | **ICP 拒批 fallback 未说** (海外 server 临时方案成本/合规?) | P5-14 |
| P1-9 | onboarding **健康度评分算法没定义** (登录频次权重? 怎么算 churn risk?) | P5-15 |
| P1-10 | **客户验证环节缺失** (Phase 4 完成后, 跑通 1-2 付费 B2B 客户 30 天没?) | 收尾 |
| P1-11 | **灰度/canary 方案没说** (新功能怎么 1% → 10% → 100% 灰度?) | P5-3, P5-5, P5-7 |

### 1.4 P2 次要问题 (可写完后再补)

| ID | 问题 |
|---|---|
| P2-1 | D1/D2/D3 写法与"完成" 混淆, 应分"task" + "day" + "DoD" |
| P2-2 | 部分 task 估时偏紧 (P5-3 6d 可能 9d, P5-6 4d 可能 7d) |
| P2-3 | 数据迁移 (P5-12) 在 P5-1 已 ship, 应从 Phase 4 范围划掉 |
| P2-4 | "走通" "做完" "ship" 4 个 task 用 4 个不同词, 应统一为 "DoD 满足" |
| P2-5 | 各 task 无 owner (谁负责, 谁 review?) — 单人全栈也要写 |

### 1.5 反模式检查

| 反模式 | 出现 | 备注 |
|---|---|---|
| **排期当计划** | ✅ | "D1 做 X" 不是 plan, 是 calendar entry |
| **任务粒度过粗** | ✅ | "D4 微信支付 API" 应拆 4 子任务 |
| **依赖嘴炮** | ✅ | "需要商户号" 没说 fallback (用 mock 跑通 e2e 也能 ship) |
| **无 buffer** | ✅ | 0d buffer, 任何 1d 延期 = 全盘崩 |
| **无客户视角** | ✅ | 全是"我做什么", 没说"客户能用上什么" |
| **假设未显化** | ✅ | 律师 1 周交付? 阿里云不挂? 汇率不变? |
| **无应急方案** | ✅ | 律师延期 2 周怎么办? 商户号拒批怎么办? |

### 1.6 缺失要素清单

| 缺失 | 影响 | 优先级 |
|---|---|---|
| 跨 task 依赖图 | 排期崩 | P0 |
| 风险登记册 (top 5) | 风险临时应对 | P0 |
| 假设清单 (汇率/法规/凭据/SLA) | 计划可执行性 | P0 |
| KPI + DoD (每 task) | 完成度不可验 | P0 |
| 紧急升级路径 (on-call rotation) | P0 事故响应 | P0 |
| Buffer 显式化 (排期 × 1.3) | 排期不崩 | P0 |
| 客户验证环节 (30 天 onboarding 跑通 1-2 客户) | 商用化实锤 | P1 |
| 灰度发布方案 (新功能 1% → 100%) | 上线事故 | P1 |
| 数据迁移对外承诺 (老用户何时迁完) | 客户沟通 | P1 |
| 财务对账 (支付 7d 内人工对账) | 漏单 | P1 |
| DB 备份恢复 SOP + RPO/RTO 数字 | 数据安全 | P1 |
| Sentry release tracking + source map | 错误定位 | P2 |
| 性能 baseline (登录 p99 < 1s?) | 回归基线 | P2 |

---

## Part 2: 修订后的详细规划 (8.5/10)

### 2.1 假设清单 (破 = plan 需调整)

| 假设 | 验证方式 | 破的影响 | 备案 |
|---|---|---|---|
| 微信支付商户号 6-08 前到位 | 1-3d 审批, 6-07 跟踪 | P5-3 延期 | 用 mock merchant 跑通 e2e, 真接入等 |
| 支付宝商户号 6-08 前到位 | 1-3d 审批 | 同上 | 同上 |
| ICP 备案 1-2 周过 | 6-15 提交后等审批 | enterprise 客户无法签约 | 海外 server 临时跑, 但 30d 内必须回迁 |
| 律师 6-15 前出稿 | 你 6-13 联系律师 | P5-4 + P5-9 延期 | 模板先用 (来源: 法斗士 / SaaS 律师库), 律师后审 |
| 阿里云 ACK 账号已开 | 你 6-10 确认 | P5-6 staging 卡 | 用 docker-compose 临时跑 (单 VM) |
| 1 full-stack + 1 PM 资源不变 | 4 周内不调配 | 实际 80% 串行, 工期 × 1.3 | buffer 加 1 周 |
| 阿里云不挂, 国内网络通 | 不可控 | staging/prod 不可达 | 监控 + 备用 region |
| 凭据 (wechat_corp_id 等) 不变 | 你 6-08 提供 | P5-2 真模式延 | 默认 mock, 真凭据后切 |
| 现有 P5-1 + P5-2 代码不返工 | 健康检查 7/7 | 历史债 | 留 2d 在 Phase 4 末尾还债 |
| 客户 1-2 个愿意当白鼠 | 7-15 内确认 | Phase 4 验不出真效果 | 你联系种子客户 |

### 2.2 风险登记册 (Top 5)

| 风险 | 概率 | 影响 | Owner | 缓解 | 触发条件 |
|---|---|---|---|---|---|
| R1: 商户号 6-15 仍未到位 | 30% | 高 (P5-3 全延) | 你 | 6-09 催 + 备用方案: 走银行对公转账 + 手工开票 | 6-15 18:00 无号 |
| R2: 律师延期 > 1 周 | 40% | 中 (P5-4 + P5-9 延) | 你 | 6-13 找备选律师 (推荐: 北京盈科/中伦) | 6-20 仍无稿 |
| R3: 部署后监控漏报 | 20% | 高 (P0 事故) | 我 | 飞书 + Sentry 双通道 + 5min 内人工 ack | 线上故障 5min 无告警 |
| R4: 客户删除数据后误伤 | 25% | 中 (数据丢失) | 我 | 软删 + 30d 宽限 + 二次确认 + 真删前 ops 审批 | 客户投诉 |
| R5: 支付重复扣款 | 15% | 高 (客诉 + 法务) | 我 | 幂等键 (order_id) + 7d 内人工对账 | 客户投诉 |

### 2.3 紧急升级路径

| 时间 | P0/P1 事故 | 升级到 |
|---|---|---|
| 工作日 09-18 | 我 (full-stack) | 你 (PM, 5min 内响应) |
| 夜间 / 周末 | 我 (on-call 7×24) | 你 (PM, 飞书 5min 内响应) |
| 我俩 30min 内无响应 | — | 阿里云工单 (P1+) + 客户群公告 (P0) |
| 支付/数据 P0 | 我 → 你 → 客户群 (4h 内公告) → 银行暂停商户号 (24h) |

**on-call rotation**: 我 (无休) + 你 (周末 备援)

### 2.4 KPI 验收 (Phase 4 完成的硬指标)

| 维度 | KPI | 验证方式 |
|---|---|---|
| 支付 | 微信支付 ¥1 + 支付宝 ¥1 真实沙箱跑通, 订单状态机闭环 (待支付/已支付/已退款/已过期) | curl + 商户后台截图 |
| 部署 | staging.airecruit.com + prod.airecruit.com 双环境, 健康检查 7/7, RPO < 1h, RTO < 30min | bash health-check.sh + 备份恢复演练 |
| 监控 | 5xx > 0.5% (1min 滑窗) / p99 > 2s / DB 连接 > 80% / LLM 失败 > 5% 4 条告警规则上线 + 飞书 webhook 接通 + 演练 1 次 | 飞书群截图 + chaos test |
| 合规 | 数据导出 JSON 完整 (20+ 表) / 数据删除 30d 宽限 + audit 落库 / Cookie banner + 隐私政策 + 服务条款上线 + 律师签字 | curl + 律师回执 |
| 法务 | signup 时勾选 ToS + PP, 落 audit | e2e 截图 |
| 监管 | AI 评分有来源 (LLM/model/version) + 人工覆盖按钮 + 申诉表单 + 7d 内回复 SLA | UI 截图 + 测试 |
| 反垃圾 | 1 手机 1 账号, LLM token 超限熔断 | 单测 |
| 客户验证 | 1-2 付费 B2B 客户 30 天 onboarding 跑通, 周活 > 60% | 客户回执 |
| 文档 | docs/p5-completion.md 类似 p5-1-completion.md 完整收尾 | 文件 |
| 测试 | pytest 0 fail, pnpm test 0 fail, health-check 7/7 | CI |

### 2.5 排期 (加 1.3 buffer = 4 周可 ship, 实际 5 周)

W1 (06-07 ~ 06-13): P5-3 支付 + P5-6 部署 (并行)
W2 (06-14 ~ 06-20): P5-4 合规 + P5-9 法务 + P5-14 ICP 启动 + P5-13 回滚
W3 (06-21 ~ 06-27): P5-5 审计 UI + P5-7 监控 + P5-8 配额 + P5-10 AI 监管
W4 (06-28 ~ 07-04): P5-11 反垃圾 + P5-15 onboarding + 收尾
W5 (07-05 ~ 07-11): Buffer (任意 task 延期用) + 1-2 客户白鼠验证

**每日节奏**: 09:00 standup (5min) + 18:00 日报 (我做, 你看)

---

## 2.6 修订后任务清单 (P0 + P1 缺口已修)

### 🔴 Week 1 (06-07 ~ 06-13) — P0 阻塞签约

#### P5-3 国内支付 (6.5d, 含 buffer)
**DoD**:
- [ ] `payment_orders` 表 (含幂等 `order_id` 唯一索引)
- [ ] `subscriptions` 表 (含 `period_start/end`, `auto_renew`, `status` 枚举)
- [ ] 状态机闭环: PENDING → PAID → REFUNDED → EXPIRED, 5 条状态转换合法
- [ ] 微信支付: 统一下单 + 回调 (rsapy 验签 + AES 解密 + 幂等 order_id)
- [ ] 支付宝: 电脑网站支付 + 回调 (RSA2 验签 + 幂等 order_id)
- [ ] **退款流程**: POST /payment/refund + 商户后台手动对账 (7d 内人工查)
- [ ] **升级/降级状态机**: starter→pro (补差价, 立即升) / pro→starter (下周期降, 不退款)
- [ ] **降级策略**: 支付失败 3 次 → 标记订阅 expired, 7d 宽限, 过后 readonly
- [ ] 前端 paywall: 超 plan quota → modal 引导升级
- [ ] 沙箱真跑 1 单 (微信 ¥1 + 支付宝 ¥1)

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 你 | 提交商户号申请 | 0d (你做) |
| D2 | migration: payment_orders + subscriptions + enum | 0.5d |
| D2 | model: PaymentOrder + Subscription | 0.5d |
| D3 | 微信支付 service (统一下单 + 回调验签) | 1d |
| D4 | 微信支付 callback endpoint + 幂等 | 0.5d |
| D4 | 支付宝 service (电脑网站支付 + 回调验签) | 1d |
| D5 | 支付宝 callback + 退款 endpoint | 1d |
| D5 | 升级/降级 endpoint + 状态机 | 0.5d |
| D6 | 前端订阅页 + paywall + 升级 modal | 1d |
| D6 | 沙箱真跑 + 截图 + e2e | 0.5d |
| **Buffer** | | **+0.5d** |

#### P5-6 生产部署 (4.5d, 含 buffer, 并行 W1)
**DoD**:
- [ ] Dockerfile.api (multi-stage, non-root user, healthcheck)
- [ ] Dockerfile.web (multi-stage, standalone output)
- [ ] docker-compose.prod.yml (postgres 独立 volume + Redis + Qdrant + MinIO + api + web + nginx)
- [ ] **CI/CD pipeline**: GitHub Actions → build → push 镜像 → 部署 staging → manual approve → 部署 prod
- [ ] **日志聚合**: stdout → 阿里云 SLS (一周可查)
- [ ] **secrets 管理**: 阿里云 KMS + .env 不入库 (检查 + pre-commit hook)
- [ ] **备份恢复 SOP**: pg_dump daily + 7-30-365 保留 + RPO 1h, 演练 1 次
- [ ] **WAF / DDoS**: 阿里云 WAF + 限 IP
- [ ] staging.airecruit.com 可访问 + SSL + 域名解析
- [ ] 监控接入 Sentry + 飞书 webhook
- [ ] **staging / prod DB 物理隔离** (不同 cluster)

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | Dockerfile.api + .dockerignore + healthcheck | 0.5d |
| D1 | Dockerfile.web (standalone output) | 0.5d |
| D2 | docker-compose.prod.yml + 阿里云 ACK 部署 | 1d |
| D2 | GitHub Actions CI/CD (build + push + deploy) | 1d |
| D3 | 阿里云 KMS secrets 接入 + .env 预提交检查 | 0.5d |
| D3 | 阿里云 SLS 日志聚合 + WAF | 0.5d |
| D4 | 域名解析 + SSL (Let's Encrypt) + staging 可访问 | 0.5d |
| D4 | 备份脚本 (pg_dump daily + 7-30-365 保留) + 演练 | 0.5d |
| D4 | 文档: deployment-runbook.md (含回滚 SOP) | 0.5d |
| **Buffer** | | **+0.5d** |

### 🟡 Week 2 (06-14 ~ 06-20) — P1 合规 + 法务

#### P5-4 个保法合规 (5.5d, 含 buffer)
**DoD**:
- [ ] `data_export_request` + `data_delete_request` 表 (user_id, status, requested_at, completed_at)
- [ ] GET /privacy/export → 异步 task → 关联 20+ 表 → JSON 打包 (字段映射文档)
- [ ] POST /privacy/delete → 软删 (user.is_active=False) + 30d 宽限 + 宽限期内禁止登录
- [ ] 定时任务 (Celery beat 每日) 硬删 30d 前的软删 user
- [ ] **外键策略**: 删除前 cascade 改 user_id → 'deleted_user_<uuid>' 占位 (保留审计链)
- [ ] 撤回删除: 30d 内用户可撤回 (恢复 is_active)
- [ ] Cookie 同意 banner (首次访问) + 隐私政策 + 服务条款链接
- [ ] /settings/privacy 用户自助入口 + 进度查询
- [ ] 律师审稿 (你对接)
- [ ] 默认不收集非必要 PII (analytics opt-in)

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | 2 表 + migration + model | 0.5d |
| D1 | data_export endpoint (async task) | 0.5d |
| D2 | data_export service (20+ 表 join → JSON) | 1d |
| D2 | data_delete endpoint (软删 + 宽限期禁止登录) | 0.5d |
| D3 | Celery beat 硬删 + 外键占位策略 | 1d |
| D3 | 撤回删除 endpoint | 0.5d |
| D4 | Cookie banner + 隐私政策/服务条款 link | 0.5d |
| D4 | /settings/privacy 入口 | 0.5d |
| D5 | 律师审稿 (你对接) | 0.5d |
| D5 | analytics opt-in | 0.5d |
| **Buffer** | | **+0.5d** |

#### P5-9 法务文件 (3d, 并行 W2)
**DoD**:
- [ ] 服务条款 ToS 模板 (律师出稿)
- [ ] 隐私政策 PP 模板 (覆盖个保法 13 条)
- [ ] DPA (数据处理协议) 模板
- [ ] signup 时勾选同意 (强制, 不勾选 = 不能注册)
- [ ] 同意动作落 audit_log
- [ ] 文档站 /legal (ToS/PP/DPA 全文)
- [ ] 律师 6-13 通知 (你) + 6-20 拿稿 (你)

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | ToS/PP/DPA 模板 (你给律师) | 0.5d |
| D2 | signup 同意 + audit hook | 0.5d |
| D3 | 文档站 /legal 路由 | 0.5d |
| **Buffer** | 律师延期 | **+1.5d** |

#### P5-14 ICP 备案 (1.5d, 启动 W2, 等审批 1-2 周)
**DoD**:
- [ ] 准备材料 (营业执照 + 法人身份证 + 域名证书) — 你 6-14 提交
- [ ] 阿里云提交 (你 6-14)
- [ ] 临时海外 server fallback (无 ICP 期间, 国内访问受限但能用)
- [ ] 备案号下来后, 切换到国内 server (D1 work)

#### P5-13 回滚方案 (2.5d, 含 buffer, 并行 W2)
**DoD**:
- [ ] alembic downgrade 全测过 (每个 migration 都能 downgrade)
- [ ] 蓝绿部署脚本 (旧版本不删, 出问题秒切)
- [ ] 5 分钟回滚 SOP (含 DB migration downgrade + 验证脚本)
- [ ] **演练 1 次**: 故意部署坏版本, 5min 内回滚, 记录用时
- [ ] on-call 培训: 我 + 你都知道怎么执行

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | alembic downgrade 测 (跑全部 history) | 0.5d |
| D1 | 蓝绿部署脚本 | 0.5d |
| D2 | 5min 回滚 SOP 文档 + 演练 1 次 | 1d |
| **Buffer** | | **+0.5d** |

### 🟢 Week 3 (06-21 ~ 06-27) — P1 运营

#### P5-5 审计日志 UI (2d)
**DoD**:
- [ ] /audit 页: 表格 (actor/action/target/ip/time) + 过滤 (action 类型, 时间范围, user) + 分页
- [ ] 详情弹窗: raw metadata
- [ ] 导出 CSV (admin 限定)
- [ ] admin role 限定 (普通 HR 看不到)
- [ ] e2e: 切换 org → 列表新行 → 点详情 → 看到 metadata

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | 表格 + 过滤 + 分页 | 1d |
| D2 | 详情弹窗 + 导出 + 权限 | 1d |

#### P5-7 监控告警 (3.5d, 含 buffer)
**DoD**:
- [ ] /metrics 完善 (Prometheus 格式): 请求延迟直方图 / 错误率 / LLM token 用量 / DB 连接池使用率
- [ ] Sentry 前后端接入 + source map + release tracking
- [ ] 4 条告警规则 + 量化阈值:
  - 5xx > 0.5% (1min 滑窗) → P1 飞书
  - p99 > 2s (1min 滑窗) → P1 飞书
  - DB 连接池 > 80% (持续 1min) → P1 飞书
  - LLM 调用失败 > 5% (5min 滑窗) → P1 飞书
  - **LLM token 用量 > plan quota 80%** → P1 飞书 (提前 1 周预警, 不超限)
- [ ] 飞书 webhook 接通 + 演练 1 次 (故意制造 5xx, 5min 内飞书响)
- [ ] **告警升级路径**: P1 5min 无 ack → 升级到你 → 30min 无 ack → 阿里云工单

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | /metrics 完善 (Prometheus) | 0.5d |
| D1 | Sentry 接入 (前后端) | 0.5d |
| D2 | 4 条告警规则 + 飞书 webhook | 0.5d |
| D2 | LLM token 用量告警 | 0.5d |
| D3 | 告警升级脚本 (5min 30min) | 0.5d |
| D3 | 演练 (故意制造 5xx + 飞书 ack) | 0.5d |
| **Buffer** | | **+0.5d** |

#### P5-8 配额/限流 (2.5d, 含 buffer)
**DoD**:
- [ ] Redis 滑动窗口限流中间件
  - **per-org 限**: 100 req/min (用 org_id 作为 key)
  - **per-user 限**: 60 req/min (用 user_id 作为 key)
  - **per-IP 限**: 30 req/min (用 IP, 匿名端点)
- [ ] 超限返 429 + Retry-After header + JSON `{error: "rate_limited", retry_after: 60}`
- [ ] per-org quota 检查 (quota_llm_tokens_per_month 等)
- [ ] 超 quota 返 429 + 飞书通知 owner
- [ ] 前端 UX: 429 时 toast "请求过快, 1min 后重试" + 链接到 "升级 plan"
- [ ] **灰度发布**: 新限流规则先 1% 流量 1 天, 没问题再 100%
- [ ] e2e: 用 ab -n 1000 模拟 1min 1000 req, 看到 429

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | 滑动窗口限流中间件 + 3 key (org/user/IP) | 1d |
| D2 | per-org quota + 飞书通知 | 0.5d |
| D2 | 前端 UX + 灰度发布开关 | 0.5d |
| **Buffer** | | **+0.5d** |

#### P5-10 AI 监管合规 (1d)
**DoD**:
- [ ] 候选人 AI 评分字段加来源: `ai_score_source` JSON {llm: "qwen3.6", model_version: "v1", prompt_hash: "abc"}
- [ ] UI 显示: 评分旁边小图标 "AI 评分" hover 显示来源
- [ ] 人工覆盖按钮: HR 可手动改分, 改后 audit 落库 (action=AI_OVERRIDE)
- [ ] 申诉表单: /candidates/[id]/appeal → 7d 内回复 SLA
- [ ] 文档: ai-disclosure.md 写清标识规则

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | 来源字段 + UI 标识 + 覆盖 + 申诉 | 1d |

### ⚪ Week 4 (06-28 ~ 07-04) — P2 收尾

#### P5-11 反垃圾/反滥用 (2d)
**DoD**:
- [ ] 阿里云短信接入 + 1 手机 1 账号
- [ ] **email 注册也限**: 1 email 1 账号 (但允许换手机绑定)
- [ ] 邀请奖励防刷: 同 IP 24h ≤ 3 邀请 / 设备指纹 (canvas hash)
- [ ] LLM token 超限熔断: per-org token 超 limit → 自动降级 (用便宜模型) + 通知 owner
- [ ] 单测: 1 手机注册 2 次 → 第二次 409

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | 阿里云短信 + 1 手机 1 账号 + email 限 | 1d |
| D2 | 邀请防刷 + LLM 熔断 | 1d |

#### P5-15 客户 onboarding runbook (2d)
**DoD**:
- [ ] 30 天 onboarding 清单: D1 培训 / D7 数据导入 / D14 流程跑通 / D30 复盘
- [ ] **数据导入**: Excel 模板 (候选人/职位) + 后台 batch import API + 进度查询
- [ ] **健康度评分算法** (P1-9 修复):
  - 登录频次 (40%): 过去 7d 日活 = 100% × N
  - 功能使用 (30%): 简历筛选/AI 评估/邀请 等核心功能触发次数
  - 工单数 (20%): 负相关
  - 推荐行为 (10%): 邀请他人 +1
  - **阈值**: < 50 = 高风险, 50-70 = 中, > 70 = 健康
- [ ] 飞书周报自动生成 (每周一 09:00 推送 owner)
- [ ] 客户首次登录后 24h 人工跟进 (你做, 飞书提醒我)

| 天 | 子任务 | 工时 |
|---|---|---|
| D1 | onboarding 清单 + Excel 模板 + import API | 1d |
| D2 | 健康度算法 + 飞书周报 | 1d |

#### Phase 4 收尾 (1d)
**DoD**:
- [ ] 全套 e2e 跑通 (P5-2 改造 8 脚本模式扩展到 P5-3 ~ P5-15)
- [ ] bash scripts/health-check.sh 7/7 + 微信登录 + 支付 e2e
- [ ] pnpm audit + python pytest 0 fail
- [ ] 写 docs/p5-completion.md (类似 p5-1-completion)
- [ ] 1-2 个付费 B2B 客户 30 天 onboarding 启动 (你联系, 我配合)

### W5 Buffer (07-05 ~ 07-11)
- 任意 task 延期用
- 客户白鼠 30 天验证
- 收尾 + commit + 文档

---

## Part 3: Verifiability Checklist (DoD 总览)

### 3.1 每个 Task 都有 DoD
详见 Part 2.6 每个 task 下的 "DoD: [...]" 列表。

### 3.2 全局完成 KPI (Phase 4 完成的硬指标)
详见 2.4 KPI 验收表。

### 3.3 失败回退
- 商户号不到位 → 用 mock merchant 跑通 e2e, 真接入等
- 律师延期 → 模板先用 (法斗士 / SaaS 律师库), 律师后审
- 阿里云挂 → 备用 region + 监控告警
- 客户验证失败 → 1 周内复盘 + 调整 onboarding

---

## Part 4: 评审结论

**修订后评分 8.5/10**:
- ✅ 清晰度 8/10 (DoD 明确)
- ✅ 可验证性 9/10 (每 task DoD + 全局 KPI)
- ✅ 完整性 8/10 (假设/风险/升级/buffer 都有了)
- ⚠️ 估算现实性 8/10 (buffer 已加, 但仍乐观)
- ✅ 风险覆盖 9/10 (top 5 风险 + owner + 触发)

**可直接 dispatch, 唯一前置**: 你 6-07 确认资源 (律师 / 商户号 / ICP 启动 / 客户白鼠)

---

## Part 5: 立即可启动的 2 个 task (0 阻塞, 今天就开)

| Task | 理由 | 工时 |
|---|---|---|
| **P5-6 部署 Dockerfile** (1.5d) | 无外部依赖, 后续 CI/CD / 监控 / secrets 都建在它上面 | 0.5d |
| **P5-5 审计 UI** (2d) | API 已 ship, UI 是纯前端, 提早 ship 提早给客户看 | 2d |
| **P5-13 alembic downgrade 测** (0.5d) | 0 阻塞, 后续所有 migration 都受益 | 0.5d |

**3 个 task 并行 3d, W1 还省下 1.5d 留给支付**。

---

下一步: 你 6-07 上午确认 律师/商户号/ICP 启动 这 3 个外部资源, 我 6-07 下午开 3 个 0 阻塞 task。
