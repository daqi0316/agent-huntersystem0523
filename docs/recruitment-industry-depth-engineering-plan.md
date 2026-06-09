# 招聘行业深度工程化重开发规划（Sisyphus 替代 Momus 审核版）

日期：2026-06-09  
范围：AI 招聘助手行业深度能力重开发  
状态：替代 Momus 工程审核后重写版，可作为下一阶段执行蓝图  

---

## 0. 替代 Momus 审核结论

原文方向正确，但仍偏“功能规划”。如果直接进入开发，会变成：表多、页面多、AI 文案多，但长期不可审计、不可统计、不可反哺。

本轮必须按你的要求重定性：

> 这不是新增几个招聘页面，而是重建招聘行业决策数据底座。

核心判断：

1. **不能按页面开发**：页面只是投影，主线应是领域模型、结构化证据、版本化标准、事件流和结果回流。
2. **不能继续堆 JSON**：JSON 可以做兼容快照，不能做统计主数据。
3. **不能只做 AI 文案**：AI 每个判断必须引用标准版本、证据、置信度和来源。
4. **不能只做 P0 功能**：P0 必须为 P1/P2 留出数据结构，不然后续薪酬、入职、试用期反哺都会变成补丁。
5. **不能推倒重来**：已有 `job_profiles`、`rejection_reasons`、`interview_evaluations`、`decision-chain` 应保留，通过新结构化子表渐进加厚。

最终路线：

> 岗位标准版本化 → 面试评分结构化 → 淘汰归因证据化 → 候选人事件流 → offer/入职结果 → 试用期与绩效反哺 → 公司招聘知识沉淀。

---

## 1. 重开发定位

### 1.1 正确定位

本项目应从“AI 招聘流程系统”升级为：

> **招聘决策操作系统 + 招聘行业数据资产平台**

长期资产不是页面，而是以下数据：

- 岗位画像标准
- 评分卡标准
- 行为锚定标准
- 候选人证据
- 面试维度得分
- 淘汰原因归因
- 薪酬风险信号
- 候选人关系事件
- offer 结果
- 入职与试用期结果
- 高绩效/失败样本回流
- 公司专属招聘知识

### 1.2 错误开发方式

禁止以下方式：

1. 先画页面，再补接口。
2. 先让 AI 生成总结，再想怎么存证据。
3. 所有复杂字段继续塞 Text JSON。
4. 岗位画像直接覆盖更新，不留历史版本。
5. 面试评价只存总分和文字结论。
6. 淘汰原因只存一个枚举，不存阶段、证据、责任归因。
7. 知识库只做 RAG 文档上传，不做来源、置信度、生效期。
8. 入职后结果不回流到前置筛选标准。

---

## 2. 当前系统证据

已有系统不是空白，必须渐进重构。

### 2.1 岗位画像基础

相关文件：

- `apps/api/app/models/job_profile.py`
- `apps/api/app/schemas/job_profile.py`
- `apps/api/app/services/job_profile.py`
- `apps/api/app/api/job_profiles.py`
- `apps/api/alembic/versions/m1_2_job_profiles.py`
- `apps/api/tests/test_job_profile_service_api.py`

现有能力：

- `hard_requirements`
- `soft_requirements`
- `evaluation_dimensions`
- `salary_band`
- `interview_focus`
- `is_active`
- seed：`Java_P7`

审核结论：可保留为聚合根，但必须新增版本、要求项、维度、锚定等结构化子表。

### 2.2 淘汰原因基础

相关文件：

- `apps/api/app/models/rejection.py`
- `apps/api/app/schemas/rejection.py`
- `apps/api/app/services/rejection.py`
- `apps/api/app/api/rejections.py`
- `apps/api/alembic/versions/m1_3_rejection_reasons.py`

已有原因码：

- `TECH_DEPTH_WEAK`
- `PROJECT_MISMATCH`
- `STABILITY_RISK`
- `SALARY_TOO_HIGH`
- `CULTURE_MISMATCH`
- `COMMUNICATION_WEAK`
- `HARD_REQUIREMENT_MISS`
- `MOTIVATION_UNCLEAR`
- `MANAGEMENT_EXPERIENCE_WEAK`
- `PROCESS_DROPOUT`

审核结论：方向正确，但还不是归因系统。需要补阶段、严重度、可预防环节、关联评分维度、证据来源。

### 2.3 面试评价基础

相关文件：

- `apps/api/app/models/interview_evaluation.py`
- `apps/api/app/api/interviews.py`

现状：

- 有面试轮次 `InterviewRound`
- 有结论 `EvaluationVerdict`
- 有总分 `overall_score`
- 有 `dimensions`，但目前是 Text JSON

审核结论：这是 P0 最大瓶颈。评分卡结构化必须优先。

### 2.4 决策链基础

相关文件：

- `apps/api/app/api/candidates.py`

现有 `/candidates/{candidate_id}/decision-chain` 已聚合：

- 候选人状态历史
- applications
- job profiles
- interviews
- interview feedback
- rejections
- missing sections

审核结论：必须继续作为核心解释层，不另起报告系统。

### 2.5 前端基础

相关目录：

- `apps/web/app/(dashboard)/screening/page.tsx`
- `apps/web/app/(dashboard)/interview`
- `apps/web/app/(dashboard)/knowledge/page.tsx`
- `apps/web/app/(dashboard)/reports/page.tsx`
- `apps/web/lib/api.ts`

审核结论：前端只做现有 dashboard 信息架构内的投影增强，不新建应用壳。

---

## 3. 领域模型总览

重开发必须围绕 3 个领域层，而不是围绕页面。

### 3.1 决策标准层 Recruiting Standard

用于定义“什么样的人适合这个岗位”。

```text
RecruitingStandard
├── JobProfile
├── JobProfileVersion
├── RequirementItem
├── EvaluationDimension
├── ScorecardTemplate
├── ScorecardDimension
├── BehaviorAnchor
└── RedFlagRule
```

长期要求：

- 可版本化
- 可解释历史决策
- 可被评分卡引用
- 可被 AI 生成问题和初筛策略引用
- 可被试用期结果反哺

### 3.2 决策证据层 Recruiting Evidence

用于记录“为什么这么判断”。

```text
RecruitingEvidence
├── ScorecardSubmission
├── DimensionScore
├── RejectionRecord
├── EvidenceRef
├── CandidateTimelineEvent
├── CompensationSignal
├── OfferNegotiationRecord
└── OnboardingOutcome
```

长期要求：

- 每个结论必须有证据
- 证据必须有来源
- 证据必须能回到候选人决策链
- AI 和人工判断使用同一证据协议

### 3.3 学习反馈层 Recruiting Learning

用于回答“哪些判断是有效的”。

```text
RecruitingLearning
├── ScorecardValidityMetric
├── ProfileOptimizationSuggestion
├── InterviewerCalibrationMetric
├── RecruitingOutcomeFeature
└── CompanyRecruitingKnowledgeItem
```

长期要求：

- 从 offer、入职、试用期和绩效回流
- 反哺岗位画像、评分卡、问题库和知识库
- 优化建议必须可接受/拒绝，不能自动覆盖标准

---

## 4. 工程化原则

### 4.1 保留聚合根，新增结构化子表

不重写：

- `job_profiles`
- `rejection_reasons`
- `interview_evaluations`

新增结构化子表承载长期统计。

兼容策略：

- 旧 JSON 字段保留为快照。
- 新表作为主数据。
- API 输出可聚合旧字段和新结构。
- 前端逐步迁移，不一次性打断现有流程。

### 4.2 标准必须版本化

以下对象必须版本化：

- 岗位画像
- 评分卡模板
- 行为锚定
- 公司招聘知识

统一规则：

- `draft` 可编辑。
- `active` 只允许一个。
- `archived` 不可编辑。
- 修改 active 标准必须 fork 新版本。
- 候选人、面试、淘汰记录必须引用当时使用的版本。

### 4.3 结论必须证据化

禁止只存：

```text
技术深度不足
```

必须存：

```text
reason_code: TECH_DEPTH_WEAK
stage: technical_interview
related_dimension: 技术深度
score: 2
evidence: 候选人无法说明 JVM GC 选择依据，也无法复盘线上性能瓶颈定位过程
source: interviewer
confidence: 0.8
standard_version_id: xxx
```

### 4.4 事件只能追加

候选人历史不可被覆盖式修改。

所有关键动作应追加事件：

- AI 初筛
- 人工初筛
- 面试安排
- 面试评分
- 淘汰
- offer
- 薪酬谈判
- 入职
- 试用期反馈
- 知识沉淀

### 4.5 报表必须导向动作

每个统计结果必须能导向业务动作。

| 发现 | 动作 |
| --- | --- |
| 硬性条件不符比例高 | 优化寻访关键词和初筛规则 |
| 薪资不匹配比例高 | 调整预算或前置薪酬沟通 |
| 技术深度低分集中 | 改面试题和技术追问 |
| 稳定性风险高 | 强化动机核验和履历核查 |
| 流程流失高 | 优化跟进 SLA |
| 面试官高分低绩效 | 做面试官校准 |

---

## 5. 统一版本化协议

### 5.1 通用字段

所有版本化对象至少包含：

```text
- id
- parent_id / entity_id
- version
- status: draft / active / archived
- effective_from
- effective_to
- change_reason
- created_by
- created_at
- activated_by
- activated_at
- archived_at
```

### 5.2 不变量

必须通过 service 层保证：

1. 同一对象同一时间只能有一个 active 版本。
2. archived 版本不可修改。
3. active 版本不可原地修改，只能新建 draft。
4. 面试、淘汰、offer、onboarding 等记录保存时必须固化引用版本。
5. 历史候选人决策链读取历史版本，不读取当前 active 版本。

---

## 6. 统一证据协议

新增通用证据引用模型：

```text
evidence_refs
- id
- candidate_id
- application_id
- source_type: resume / interview / scorecard / rejection / timeline / compensation / onboarding / knowledge
- source_id
- quote
- normalized_claim
- confidence
- created_by_type: human / ai / system
- created_by_id
- created_at
```

使用规则：

- 面试维度分必须引用证据或填写 evidence 文本。
- 淘汰记录必须引用证据。
- AI 初筛必须引用简历片段或知识来源。
- decision-chain 展示结论时必须能展开证据。
- 低分和高分都要证据，防止虚低和虚高。

---

## 7. 统一候选人事件流协议

候选人时间线应升级为底层事件流。

```text
candidate_timeline_events
- id
- candidate_id
- application_id
- event_type: screening / call / wechat / email / interview / scorecard / offer / rejection / followup / note / commitment / risk / onboarding / probation
- title
- content
- occurred_at
- actor_type: human / ai / system / integration
- actor_id
- source_module
- metadata JSON
- evidence_refs JSON
- created_at
```

要求：

- 人工、系统、AI 都写入同一时间线。
- 业务模块不得各建一套孤立 timeline。
- decision-chain 从事件流中提取关键证据。
- followup task、commitment、risk 都应能关联事件。

---

## 8. AI 判断审计协议

任何 AI 输出如果影响招聘判断，必须落审计记录。

```text
ai_decision_audits
- id
- candidate_id
- application_id
- decision_type: screening / scorecard_assist / rejection_suggest / offer_risk / onboarding_risk / profile_suggestion
- model_name
- prompt_version
- input_refs JSON
- output_summary
- cited_standard_version_ids JSON
- cited_evidence_ref_ids JSON
- confidence
- human_confirmed
- confirmed_by
- confirmed_at
- created_at
```

硬规则：

1. AI 不能直接覆盖岗位标准。
2. AI 不能直接淘汰候选人，只能生成建议或草稿。
3. AI 输出必须引用证据。
4. AI 输出必须记录 prompt/model 版本。
5. 涉及淘汰、offer、入职风险的 AI 结论必须支持人工确认。

---

## 9. P0：决策标准层，必须先做

P0 目标不是“功能上线”，而是建立可长期演进的招聘决策主数据。

### 9.1 P0-A 决策标准底座（第一开发包）

这是第一优先级，替代原文“先做评分卡页面”的思路。

#### 目标

建立：

- 岗位画像版本
- 结构化评分卡
- 行为锚定
- 评分提交
- 维度证据
- 旧评价兼容
- decision-chain 投影

#### 数据模型

```text
job_profile_versions
- id
- job_profile_id
- version
- status
- change_reason
- effective_from
- effective_to
- created_by
- activated_by
- created_at
- activated_at

job_profile_requirement_items
- id
- profile_version_id
- type: hard / soft
- category: education / years / skill / communication / culture / motivation / stability
- label
- description
- must_have
- weight
- evidence_required
- red_flag_if_missing
- order_index

job_profile_dimensions
- id
- profile_version_id
- name
- category
- weight
- description
- must_have
- key_questions JSON
- red_flags JSON
- order_index

scorecard_templates
- id
- job_profile_id
- profile_version_id
- name
- round_type: phone_screen / technical / behavioral / final / manager
- status: draft / active / archived
- total_weight
- created_by
- created_at

scorecard_dimensions
- id
- scorecard_template_id
- name
- category
- weight
- description
- required
- order_index

scorecard_behavior_anchors
- id
- dimension_id
- score: 1..5
- anchor_text
- evidence_examples JSON
- red_flags JSON

interview_scorecard_submissions
- id
- interview_id
- candidate_id
- application_id
- scorecard_template_id
- interviewer_id
- overall_score
- verdict: strong_hire / hire / consider / pass
- summary
- risk_flags JSON
- submitted_at

interview_scorecard_dimension_scores
- id
- submission_id
- dimension_id
- score
- evidence
- confidence
```

#### API

```text
GET    /api/v1/job-profiles
GET    /api/v1/job-profiles/{id}
POST   /api/v1/job-profiles/{id}/versions
POST   /api/v1/job-profiles/{id}/versions/{version_id}/activate

GET    /api/v1/scorecards/templates
POST   /api/v1/scorecards/templates
GET    /api/v1/scorecards/templates/{id}
PUT    /api/v1/scorecards/templates/{id}
POST   /api/v1/scorecards/templates/from-job-profile/{profile_id}
GET    /api/v1/interviews/{id}/scorecard
POST   /api/v1/interviews/{id}/scorecard-submissions
GET    /api/v1/candidates/{id}/scorecards
```

#### 强约束

- 维度权重总和必须等于 1.0。
- 每个必填维度必须打分。
- 分数范围只能是 1..5。
- 每个维度都必须有证据。
- active 模板不可原地修改。
- 面试提交后必须固化 scorecard_template_id。
- 新评分卡提交后同步或派生旧 `interview_evaluations.overall_score`、`verdict`、`dimensions`，保证旧页面不坏。

#### 前端

只做必要投影：

```text
/dashboard/job-profiles
/dashboard/job-profiles/[id]
/dashboard/scorecards
/dashboard/scorecards/[id]
/dashboard/interview/[id]/scorecard
```

#### 验收场景

Java P7 候选人完整走通：

1. 候选人关联岗位画像版本。
2. 系统生成或选择专业面评分卡。
3. 面试官按维度打分。
4. 每个维度填写证据。
5. 总分和 verdict 自动计算或校验。
6. 旧 `interview_evaluations` 兼容可读。
7. decision-chain 展示评分卡、维度分、证据和标准版本。

### 9.2 P0-B 淘汰原因归因系统

在 P0-A 后做。

#### 字段增强

`rejection_reasons` 增加：

```text
parent_id
severity: low / medium / high
stage_applicability JSON
preventable_by: sourcing / screening / scorecard / compensation / process / none
```

`candidate_rejection_records` 增加：

```text
source: human / ai / interviewer / system
confidence
is_primary
related_dimension_id
related_scorecard_submission_id
evidence_ref_id
```

#### 验收标准

- 每次淘汰必须结构化记录。
- 淘汰原因必须有证据。
- 能按岗位、阶段、原因统计。
- AI 筛选结论必须引用标准原因码。
- 报表能展示原因分布和建议动作。

### 9.3 P0-C 决策链投影增强

目标：让 candidate decision-chain 成为所有证据的统一解释面。

必须展示：

- 岗位画像版本
- 评分卡模板版本
- 维度得分
- 行为证据
- 淘汰原因
- 薪酬风险占位
- timeline 关键事件
- AI 判断审计记录

---

## 10. P1：招聘经营层

P1 目标是把系统从流程工具升级为招聘经营系统。

### 10.1 候选人关系时间线

基于统一 `candidate_timeline_events`，新增：

```text
candidate_followup_tasks
- id
- candidate_id
- application_id
- due_at
- task_type
- title
- status: pending / done / overdue / cancelled
- priority
- owner_id
- auto_generated
- trigger_rule

candidate_commitments
- id
- candidate_id
- application_id
- promised_by: candidate / recruiter / interviewer / hiring_manager
- content
- due_at
- status
- related_event_id
```

自动提醒规则：

- 3 天无回复：提醒跟进。
- 7 天无流程进展：提醒 HR 检查。
- 面试后 24 小时未反馈：提醒面试官。
- offer 发出 48 小时无回应：提醒谈判。
- 入职前 7 天：确认材料和意愿。
- 入职前 1 天：确认到岗。

### 10.2 薪酬数据库

```text
compensation_benchmarks
- id
- industry
- city
- job_family
- job_title
- level
- company_type
- company_name
- base_min
- base_p50
- base_max
- total_min
- total_p50
- total_max
- currency
- period
- data_source
- confidence
- sample_size
- effective_date

candidate_compensation_expectations
- id
- candidate_id
- current_base
- current_total
- expected_base
- expected_total
- minimum_acceptable
- notice_period
- competing_offers JSON
- notes

offer_negotiation_records
- id
- candidate_id
- application_id
- job_id
- expected_total
- first_offer_total
- final_offer_total
- market_p50
- budget_min
- budget_max
- negotiation_status
- accepted
- reject_reason
- notes
```

验收：

- 支持按城市、职级、岗位查薪酬。
- 支持候选人期望薪酬记录。
- 支持 offer 谈判结果记录。
- 支持薪酬风险标签。
- 支持分析薪资导致流失比例。

### 10.3 入职后跟踪

```text
onboarding_trackings
- id
- candidate_id
- application_id
- offer_id
- hire_date
- department
- manager_id
- mentor_id
- status: preboarding / onboarded / probation / probation_passed / probation_failed / resigned
- risk_level
- created_at

onboarding_checkpoints
- id
- onboarding_id
- checkpoint_type: day_1 / day_7 / month_1 / month_3 / month_6
- due_at
- completed_at
- status
- owner_id
- summary
- risk_flags JSON

probation_feedbacks
- id
- onboarding_id
- checkpoint_id
- reviewer_id
- performance_score
- culture_fit_score
- ramp_up_score
- communication_score
- retention_risk
- feedback_text
- pass_probation
```

验收：

- offer accepted 后创建 onboarding tracking。
- 自动生成 1/3/6 月检查点。
- 记录试用期反馈。
- 统计试用期通过率。
- 试用期结果能关联候选人、岗位画像版本、评分卡版本。

---

## 11. P2：数据智能层

P2 目标是形成长期壁垒。

### 11.1 招聘结果回流

需要回答：

- 哪些岗位画像特征预测试用期成功？
- 哪些面试维度最有效？
- 哪些淘汰原因可以前置规避？
- 哪些面试官评分偏差大？
- 哪类候选人 offer 成功率高？

数据模型：

```text
scorecard_validity_metrics
- id
- scorecard_template_id
- dimension_id
- interviewer_id
- sample_size
- correlation_with_probation
- false_positive_rate
- false_negative_rate
- avg_score
- actual_success_rate

profile_optimization_suggestions
- id
- job_profile_id
- profile_version_id
- suggestion_type: weight_change / new_requirement / remove_requirement / new_question / red_flag
- evidence_summary
- confidence
- status: proposed / accepted / rejected

recruiting_outcome_features
- id
- candidate_id
- application_id
- onboarding_id
- feature_name
- feature_value
- source
- outcome_label
```

### 11.2 公司专属招聘知识库

知识库不能只是 RAG 文档库，必须结构化、可过期、可引用。

```text
company_recruiting_knowledge_items
- id
- org_id
- company_id
- team_id
- job_profile_id
- knowledge_type: interviewer_preference / team_culture / hiring_manager_preference / historical_lesson / compensation_policy / rejection_pattern / successful_profile / interview_question
- title
- content
- source
- confidence
- effective_from
- effective_to
- tags JSON
- embedding_id
- created_at
```

AI 使用知识库的场景：

- 生成 JD
- 构建岗位画像
- 初筛候选人
- 生成面试问题
- 评估面试反馈
- offer 谈判建议
- 淘汰原因复盘
- 入职风险预警

硬规则：

- AI 输出必须引用知识来源。
- 过期知识不得参与新判断。
- 自动沉淀知识必须先进入 proposed 状态。
- 人工确认后才能成为 active 知识。

---

## 12. 服务层与模块边界

不要继续把所有新逻辑堆到通用 `services/`。

建议新增领域目录：

```text
apps/api/app/domains/recruiting_standards/
- job_profile_version_service.py
- requirement_item_service.py
- scorecard_template_service.py
- behavior_anchor_service.py
- versioning_service.py

apps/api/app/domains/interview_evidence/
- scorecard_submission_service.py
- dimension_score_service.py
- evaluation_sync_service.py

apps/api/app/domains/decision_chain/
- decision_chain_projection_service.py
- evidence_projection_service.py

apps/api/app/domains/recruiting_events/
- timeline_event_service.py
- followup_task_service.py

apps/api/app/domains/recruiting_outcomes/
- onboarding_service.py
- probation_feedback_service.py

apps/api/app/domains/recruiting_intelligence/
- validity_metric_service.py
- profile_optimization_service.py
- recruiting_knowledge_service.py
```

边界规则：

- API 层只做请求/响应。
- Service 层做业务不变量。
- Model 层不藏业务逻辑。
- AI 层不能直接写核心标准，只能写建议、审计、草稿。
- decision-chain 是投影层，不是业务写入入口。

---

## 13. 数据迁移策略

### 13.1 原则

不做一次性大迁移，采用双写/派生/懒迁移。

### 13.2 迁移阶段

#### 阶段 A：建新表

- Alembic 创建新结构化表。
- 不删除旧字段。
- 不改变旧 API 行为。

#### 阶段 B：新写入走新表

- 新评分卡提交写入结构化表。
- 同步派生旧 `interview_evaluations`。
- decision-chain 优先读新结构，缺失时读旧数据。

#### 阶段 C：历史数据懒迁移

- 旧 `dimensions` JSON 可按需转换为 snapshot。
- 不要求一次性转换所有历史记录。
- 转换失败不阻断主流程。

#### 阶段 D：统计只读新表

- 报表、分析、P2 指标只使用结构化主数据。
- JSON 字段只做历史展示和兼容。

---

## 14. 推荐开发顺序

### Milestone 1：P0 决策标准层，2-3 周

#### M1.1 P0-A 决策标准底座

- 岗位画像版本表。
- 画像要求项与维度表。
- 评分卡模板、维度、行为锚定。
- 评分提交和维度分。
- 旧评价兼容同步。
- decision-chain 展示评分卡证据。

#### M1.2 P0-B 淘汰归因系统

- 扩展 rejection taxonomy。
- 淘汰记录关联评分卡维度。
- 淘汰证据引用。
- 按岗位、阶段、原因统计。

#### M1.3 P0-C 决策链增强

- 聚合标准版本。
- 聚合证据。
- 聚合 AI 审计。
- 聚合 timeline 关键事件。

### Milestone 2：P1 招聘经营层，3-4 周

- 候选人统一事件流。
- 跟进任务和承诺。
- 薪酬数据库。
- offer 谈判记录。
- onboarding 和 probation feedback。

### Milestone 3：P2 数据智能层，4-6 周

- scorecard validity。
- profile effectiveness。
- interviewer calibration。
- company recruiting knowledge。
- profile optimization suggestions。

---

## 15. 第一开发包冻结范围

第一包名称：

> P0-A 招聘决策标准底座

### 15.1 必做

1. Alembic migration：新增版本、评分卡、维度分相关表。
2. SQLAlchemy model：与 DB schema 一致。
3. Pydantic schema：校验权重、分数、必填证据。
4. Service：封装版本规则、权重规则、提交规则。
5. API：评分卡模板和面试评分提交。
6. 兼容：同步旧 `interview_evaluations`。
7. decision-chain：展示评分卡结果和证据。
8. 前端：最小可用评分卡填写页。
9. 测试：后端单测 + 前端 smoke/e2e。
10. 健康检查：`bash scripts/health-check.sh` 6/6 pass。

### 15.2 不做

- 不做薪酬数据库。
- 不做入职后跟踪。
- 不做复杂 AI 优化建议。
- 不做全量历史数据迁移。
- 不重写 interview 页面。
- 不做大屏报表。
- 不引入新的应用壳。

### 15.3 验收标准

- 8 个 P0 岗位模板可逐步 seed，但第一包至少保证 Java P7 完整可用。
- 每个评分卡维度权重合计为 1.0。
- 每个维度都有 1/3/5 行为锚定。
- 面试提交后生成结构化维度分。
- 高分低分均要求证据。
- 旧面试评价页面不坏。
- decision-chain 能展示评分卡证据链。
- 健康检查 6/6 pass。

---

## 16. 工程验收门禁

每个开发包都必须满足：

1. Alembic migration 可正向升级。
2. SQLAlchemy model 与 DB schema 一致。
3. Pydantic schema 有校验。
4. Service 层覆盖核心不变量。
5. API 有单测。
6. 前端关键流程有 smoke/e2e。
7. decision-chain 能展示新增证据。
8. AI 判断有审计记录。
9. 不破坏旧页面和旧 API。
10. 修改后必须跑 `bash scripts/health-check.sh`，且 6/6 pass。

---

## 17. 风险与回滚

### 17.1 主要风险

| 风险 | 后果 | 规避 |
| --- | --- | --- |
| 版本规则没做扎实 | 历史决策不可解释 | active/archive 不变量写入 service |
| 评分卡只做页面 | 后续无法统计 | 先做结构化主数据 |
| 证据协议缺失 | AI 结论不可审计 | 所有结论引用 evidence_ref |
| 事件流不统一 | 决策链碎片化 | 所有模块写 candidate_timeline_events |
| 历史迁移过大 | 开发阻塞 | 懒迁移，旧字段兼容 |
| P1/P2 过早开发 | 地基未稳 | 必须先完成 P0-A/P0-B |

### 17.2 回滚策略

- 新表迁移可独立回滚。
- 旧字段保留，旧页面可继续使用。
- 新 API 可关闭入口，不影响旧流程。
- 新评分卡失败时，保留旧 `interview_evaluations` 写入路径。

---

## 18. 最终冻结决策

本轮替代 Momus 审核后的冻结路线：

1. **重开发不是重写系统**，而是重建招聘决策数据底座。
2. **P0 先做决策标准层**：版本化岗位画像、结构化评分卡、证据化淘汰归因。
3. **P1 再做招聘经营层**：候选人事件流、薪酬、offer、入职和试用期。
4. **P2 最后做数据智能层**：评分卡有效性、画像优化、面试官校准、公司知识库。
5. **第一开发包改为 P0-A 招聘决策标准底座**，不是单纯评分卡页面。
6. **所有开发以 decision-chain 可解释为最终产品面**。
7. **所有 AI 判断必须可审计、可引用、可人工确认**。

最终原则：

> 不做表面功能，不做孤立页面，不做不可审计 AI。  
> 做长期可解释、可统计、可反哺的招聘行业数据资产。
