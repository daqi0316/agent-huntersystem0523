# AI 招聘 Agent 深度缺口填补规划

> **目标**：把 16 年猎头 + 甲方 HR 经验，结构化编码进 AI 招聘 Agent 系统
> 
> **原则**：先 P0（骨架）→ 再 P1（血肉）→ 后 P2（闭环）
> 
> **输出**：每个层级有具体的数据结构、Prompt 设计、MCP 工具定义

---

## 目录

- [一、用户交互层深度规划](#一用户交互层深度规划)
- [二、编排层深度规划](#二编排层深度规划)
- [三、业务 Agent 层深度规划](#三业务-agent-层深度规划)
  - [3.1 简历解析 Agent](#31-简历解析-agent)
  - [3.2 寻访 Agent](#32-寻访-agent)
  - [3.3 筛选 Agent](#33-筛选-agent)
  - [3.4 面试协调 Agent](#34-面试协调-agent)
  - [3.5 薪酬谈判 Agent](#35-薪酬谈判-agent)
  - [3.6 入职跟进 Agent](#36-入职跟进-agent)
- [四、共享层深度规划](#四共享层深度规划)
  - [4.1 记忆层](#41-记忆层)
  - [4.2 知识库](#42-知识库)
  - [4.3 通知层](#43-通知层)
  - [4.4 权限层](#44-权限层)
- [五、MCP Server + 业务系统深度规划](#五mcp-server--业务系统深度规划)
  - [5.1 MCP 工具定义](#51-mcp-工具定义)
  - [5.2 数据库 Schema](#52-数据库-schema)
- [六、实施路线图](#六实施路线图)

---

## 一、用户交互层深度规划

### 1.1 招聘术语词典 + 意图理解增强

**现状问题**：意图识别只理解"动词"（筛简历、安排面试），不理解"招聘决策意图"。

**深度增强**：

```yaml
# 招聘术语词典（意图识别层注入）
term_dictionary:
  # 稳定性相关
  稳定性不好:
    - 频繁跳槽（3年内换工作>2次）
    - 每段工作<1.5年
    - 空窗期>6个月且无合理解释
    - 行业波动期离职（如教培、地产下行期）

  技术可以但文化不匹配:
    - 面试中表现出过度自我（不配合团队）
    - 对前公司/前领导负面评价过多
    - 价值观与公司使命不符
    - 工作风格与团队节奏冲突（如狼性文化 vs 佛系）

  能扛住双十一流量:
    - 高并发经验（QPS>10K）
    - 电商行业背景
    - 大促期间稳定性保障经验
    - 容量规划与限流降级实战经验

  # 薪酬相关
  期望过高:
    - 期望薪资 > 岗位预算上限 120%
    - 期望薪资 > 市场 P75 水平
    - 总包构成不合理（base 过低，期权期望过高）
```

**意图识别增强（Orchestrator Prompt 片段）**：

```markdown
## 意图识别规则

### 第一层：动作意图（现有）
- 筛简历、安排面试、发 Offer、查进度

### 第二层：招聘决策意图（新增）
当用户输入包含以下特征时，识别为"决策意图"：

| 用户表达 | 识别为 | 需要调用的 Agent |
|----------|--------|----------------|
| "这个候选人技术还行，但稳定性不好" | 风险评估意图 | 筛选 Agent + 寻访 Agent |
| "帮我再找找类似的，但要更稳定" | 寻访优化意图 | 寻访 Agent（带排除条件） |
| "P7 的 Java，分布式事务要问到什么深度" | 面试标准查询 | 面试协调 Agent |
| "这个 offer 能不能再加 5k" | 谈判策略意图 | 薪酬谈判 Agent |

### 第三层：隐含意图（新增）
- "最近 Java 好难招" → 隐含：市场供需分析 + 寻访策略调整
- "这个候选人上次说考虑创业" → 隐含：关系维护提醒 + 风险标记
```

---

### 1.2 招聘效能看板（管理后台增强）

**你之前擅长的量化指标，需要内置到系统里**：

```json
{
  "dashboard_metrics": {
    "效能指标": {
      "OTD": {
        "definition": "从需求确认到候选人入职的平均天数",
        "target": "< 45天",
        "current": "38天",
        "trend": "↓ 5天（环比）"
      },
      "试用期通过率": {
        "definition": "入职3个月内通过试用期的比例",
        "target": "> 85%",
        "current": "88%",
        "trend": "↑ 3%（同比）"
      },
      "关键岗位离职率": {
        "definition": "入职1年内主动离职的关键岗位比例",
        "target": "< 10%",
        "current": "8%",
        "trend": "↓ 2%（同比）"
      }
    },
    "漏斗指标": {
      "简历筛选通过率": "15%",
      "初筛通过率": "35%",
      "一面通过率": "45%",
      "二面通过率": "60%",
      "Offer 接受率": "75%",
      "入职率": "90%"
    },
    "成本指标": {
      "单岗招聘成本": "￥12,000",
      "猎头费率": "20%",
      "内推占比": "30%",
      "主动寻访占比": "40%"
    }
  }
}
```

---

## 二、编排层深度规划

### 2.1 候选人状态机（路由决策核心）

**现状**：基于"用户意图"做简单路由。

**深度增强**：基于"候选人状态 + 用户意图"做动态路由。

```yaml
# 候选人状态机定义
candidate_state_machine:
  states:
    - 新投递
    - 初筛中        # 简历解析 Agent 处理中
    - 初筛通过      # 进入寻访/筛选池
    - 初筛淘汰      # 终态，记录淘汰原因
    - 一面待安排
    - 一面已安排
    - 一面待反馈    # 面试官还没提交评价
    - 一面通过
    - 一面淘汰      # 终态
    - 二面待安排
    - 二面已安排
    - 二面待反馈
    - 二面通过
    - 二面淘汰      # 终态
    - HR 面待安排
    - HR 面已安排
    - HR 面待反馈
    - Offer 谈判中   # 薪酬谈判 Agent 介入
    - Offer 已发
    - Offer 已接受
    - Offer 已拒绝   # 终态，记录拒绝原因
    - 入职待报到
    - 已入职
    - 试用期跟踪中   # 入职跟进 Agent 介入
    - 试用期通过     # 终态，成功
    - 试用期淘汰     # 终态，记录淘汰原因，回流筛选标准

  transitions:
    # 每个状态转换触发什么 Agent
    新投递 → 初筛中:
      trigger: 自动
      agent: 简历解析 Agent
      tools: [parse_resume, match_job_profile, risk_check]

    初筛通过 → 一面待安排:
      trigger: 自动
      agent: 面试协调 Agent
      tools: [generate_interview_guide, match_interviewer, schedule_interview]

    一面通过 → 二面待安排:
      trigger: 面试官提交评价后
      condition: 评分 >= 3.5/5
      agent: 面试协调 Agent
      tools: [update_candidate_state, notify_hiring_manager, schedule_next_round]

    二面通过 → Offer 谈判中:
      trigger: 自动
      agent: 薪酬谈判 Agent
      tools: [calculate_offer_package, generate_negotiation_strategy, check_budget]

    Offer 已接受 → 入职待报到:
      trigger: 候选人确认后
      agent: 入职跟进 Agent
      tools: [send_onboarding_kit, schedule_first_day, prepare_workspace]

    已入职 → 试用期跟踪中:
      trigger: 入职当天
      agent: 入职跟进 Agent
      tools: [schedule_30day_checkin, schedule_90day_checkin, schedule_180day_checkin]
```

---

### 2.2 动态路由规则（Orchestrator 核心逻辑）

```python
# 伪代码：Orchestrator 路由决策
def route_task(user_intent, candidate_state, context):
    # 路由决策基于三层信息：
    # 1. 用户意图（说什么）
    # 2. 候选人状态（在哪一步）
    # 3. 上下文信息（历史沟通、风险标记）

    # 场景1：用户说"安排面试"，但候选人状态是"一面待反馈"
    if user_intent == "安排面试" and candidate_state == "一面待反馈":
        return {
            "action": "提醒面试官提交反馈",
            "agent": "通知 Agent",
            "message": "面试官 XXX 还未提交一面反馈，请先催促反馈后再安排二面"
        }

    # 场景2：用户说"这个候选人不错"，但候选人状态是"初筛中"
    if user_intent == "正面评价" and candidate_state == "初筛中":
        return {
            "action": "加速流转",
            "agent": "筛选 Agent",
            "tools": ["fast_track_review", "generate_interview_guide"],
            "note": "用户主观评价积极，建议优先安排"
        }

    # 场景3：用户说"再找找类似的"，隐含排除当前候选人的某些特征
    if user_intent == "寻访优化":
        exclusion_criteria = extract_exclusion_criteria(context)
        return {
            "action": "优化寻访条件",
            "agent": "寻访 Agent",
            "tools": ["search_candidates"],
            "params": {
                "must_have": context.get("must_have"),
                "must_not_have": exclusion_criteria,
                "preference": context.get("preference")
            }
        }

    # 场景4：用户提到"上次说考虑创业" → 关系维护提醒
    if "创业" in user_intent and "上次" in context:
        return {
            "action": "关系维护",
            "agent": "寻访 Agent",
            "tools": ["send_follow_up", "update_relationship_timeline"],
            "note": "该候选人 3 个月前表达创业意向，建议温和跟进，了解最新动态"
        }
```

---

## 三、业务 Agent 层深度规划

### 3.1 简历解析 Agent

**现有工具**：`parse_resume`、`extract_skills`、`match_keywords`

**深度增强后**：

```yaml
# 简历解析 Agent - 深度增强版
resume_parser_agent:
  tools:
    # 工具1：结构化解析（原有）
    parse_resume:
      input: [resume_pdf, resume_text]
      output: 
        - basic_info: {name, age, education, contact}
        - work_experience: [{company, title, period, description}]
        - skills: [skill_list]

    # 工具2：招聘风险标记（新增 - 核心深度）
    risk_assessment:
      input: [parsed_resume, job_profile]
      output:
        risk_flags:
          - type: "频繁跳槽"
            severity: "高/中/低"
            evidence: "3年内换工作4次，平均 tenure 8个月"
            impact: "试用期离职风险增加40%"
          - type: "空窗期"
            severity: "中"
            evidence: "2022.03-2022.12 无工作经历"
            explanation: "候选人自述'休息+学习'，需面试中核实"
          - type: "学历断层"
            severity: "低"
            evidence: "本科毕业5年后才出现第一份工作"
            note: "需核实是否有非全日制经历未写明"
        risk_score: 65  # 0-100，越高风险越大
        recommendation: "建议初筛面试重点核实空窗期和跳槽原因"

    # 工具3：岗位匹配度评分（新增 - 核心深度）
    match_scoring:
      input: [parsed_resume, job_profile, scoring_criteria]
      output:
        overall_score: 78  # 0-100
        dimension_scores:
          - dimension: "技术深度"
            weight: 30%
            score: 82
            evidence: "5年 Java 经验，有分布式系统实战经验，GitHub 有2K star项目"
          - dimension: "项目经验"
            weight: 25%
            score: 75
            evidence: "主导过2个中大型项目，但缺乏高并发场景"
          - dimension: "稳定性"
            weight: 20%
            score: 60
            evidence: "3年换2次工作，但都在同行业内"
          - dimension: "文化匹配"
            weight: 15%
            score: 85
            evidence: "前公司文化与我司相似，面试中需确认"
          - dimension: "潜力"
            weight: 10%
            score: 80
            evidence: "有技术博客，持续学习，GitHub 活跃"
        gap_analysis:
          - "缺少云原生实战经验（K8s 仅了解层面）"
          - "无团队管理经验（目标岗位需要带3-5人）"
        recommendation: "技术一面重点考察云原生，若通过建议二面考察管理能力"

  scoring_criteria:  # 岗位画像定义的评分标准
    Java_P7:
      技术深度:
        - score: 5, evidence: "能深入讲解 JVM 调优、GC 算法选择、线上问题排查"
        - score: 4, evidence: "熟悉常用框架原理，能排查常见问题"
        - score: 3, evidence: "能完成日常开发，但对原理理解不深"
        - score: 2, evidence: "仅了解基本概念，缺乏实战经验"
      稳定性:
        - score: 5, evidence: "每段工作>3年，或合理晋升跳槽"
        - score: 3, evidence: "2-3年一跳，行业内有合理性"
        - score: 1, evidence: "频繁跳槽，无合理解释"
```

---

### 3.2 寻访 Agent

**现有工具**：`search_talent_pool`、`search_job_boards`、`cold_outreach`

**深度增强后**：

```yaml
# 寻访 Agent - 深度增强版
sourcing_agent:
  tools:
    # 工具1：人才地图查询（替代简单搜索）
    talent_map_query:
      input: [job_profile, target_companies, constraints]
      output:
        target_companies:
          - company: "阿里巴巴"
            org_structure: "淘天集团-技术部-Java 中间件团队"
            key_teams: ["高并发架构组", "交易系统组"]
            talent_quality: "P7 质量高，P8 竞争激烈"
            poaching_difficulty: "高（期权未归属）"
            suggested_approach: "通过技术社区接触，或等待期权归属期"
          - company: "字节跳动"
            org_structure: "抖音电商-后端架构"
            key_teams: ["交易核心组", "推荐架构组"]
            talent_quality: "技术能力强，但工作强度大，流动性较高"
            poaching_difficulty: "中"
            suggested_approach: "强调 work-life balance 和长期发展"

        candidate_pipeline:
          - name: "张三"
            current_company: "阿里巴巴"
            current_title: "高级 Java 工程师"
            estimated_level: "P7"
            match_score: 85
            contact_history: "2025-11 通过技术大会认识，交换了微信"
            last_contact: "2026-03-15"
            status: "被动观望"
            suggested_next_step: "分享我司技术博客，保持弱联系"

    # 工具2：寻访策略生成（新增）
    sourcing_strategy:
      input: [job_profile, market_analysis, historical_data]
      output:
        primary_channels:
          - channel: "主动寻访"
            weight: 40%
            tactics: ["LinkedIn 定向搜索", "GitHub 技术贡献者筛选", "技术社区 KOL"]
          - channel: "内部推荐"
            weight: 30%
            tactics: ["员工推荐奖励计划", "内部人才 mapping", "离职员工回流"]
          - channel: "被动引流"
            weight: 20%
            tactics: ["技术博客/公众号", "开源项目", "技术大会演讲"]
          - channel: "猎头合作"
            weight: 10%
            tactics: ["独家猎头协议", "按结果付费", "保证期条款"]

        timeline:
          - week: 1-2
            focus: "主动寻访，建立50人目标清单"
            expected_output: "20个初步接触"
          - week: 3-4
            focus: "筛选和初筛面试"
            expected_output: "10个进入一面"
          - week: 5-6
            focus: "深度面试和 Offer 谈判"
            expected_output: "2-3个 Offer"
          - week: 7-8
            focus: "入职跟进"
            expected_output: "1-2个成功入职"

        risk_mitigation:
          - "若2周内主动寻访不足20人，启动猎头合作"
          - "若4周内无合适候选人进入二面，调整岗位画像或薪资预算"

    # 工具3：关系维护（新增 - 长期深度）
    relationship_management:
      input: [candidate_id, relationship_timeline]
      output:
        follow_up_plan:
          - date: "2026-06-15"
            action: "发送行业报告（技术趋势）"
            channel: "微信"
            message_template: "最近看到一篇关于云原生架构的深度文章，想到你对这块有研究，分享给你..."
          - date: "2026-06-30"
            action: "邀请参加技术分享会"
            channel: "邮件"
            note: "我司 CTO 将在7月做技术分享，适合邀请技术候选人参加"

        risk_alerts:
          - "候选人 LinkedIn 更新为'Open to work' → 立即联系"
          - "候选人 GitHub 30天无提交 → 可能工作繁忙或离职，适时关心"
          - "候选人前公司大规模裁员 → 可能被动求职，主动接触"
```

---

### 3.3 筛选 Agent

**现有工具**：`filter_by_criteria`、`rank_candidates`、`send_rejection`

**深度增强后**：

```yaml
# 筛选 Agent - 深度增强版
screening_agent:
  tools:
    # 工具1：结构化筛选（替代简单过滤）
    structured_screening:
      input: [candidate_list, job_profile, screening_criteria]
      output:
        screened_candidates:
          - candidate_id: "C_001"
            name: "张三"
            pass: true
            dimension_scores:
              - dimension: "硬性条件"
                score: 100
                check: "本科/5年经验/Java 精通"
              - dimension: "技术匹配"
                score: 85
                check: "有高并发经验，但缺乏 K8s 实战经验"
              - dimension: "稳定性"
                score: 70
                check: "3年2跳，但都在电商行业"
              - dimension: "薪资匹配"
                score: 90
                check: "期望45k，预算40-50k"
            overall_score: 86
            decision: "通过初筛，建议一面"
            notes: "技术一面重点考察 K8s，若通过可推进"

          - candidate_id: "C_002"
            name: "李四"
            pass: false
            rejection_reason:
              primary: "技术深度不足"
              detail: "5年经验但项目描述停留在 CRUD 层面，无架构设计经验"
              category: "技术不够"  # 结构化淘汰原因
            suggested_action: "若未来有初级岗位开放，可重新激活"

    # 工具2：淘汰原因分析（新增 - 数据闭环核心）
    rejection_analysis:
      input: [rejection_records, time_range]
      output:
        rejection_distribution:
          - reason: "技术深度不足"
            count: 15
            percentage: 30%
            trend: "↑ 5%（环比）"
            insight: "近期寻访渠道质量下降，或岗位画像要求过高"
            suggested_action: "优化寻访关键词，增加'架构设计'、'系统优化'等筛选条件"
          - reason: "薪资期望过高"
            count: 10
            percentage: 20%
            trend: "→ 持平"
            insight: "市场薪资水平上涨，需评估是否调整预算"
            suggested_action: "与 HRBP 沟通，申请薪资带宽调整或增加签字费"
          - reason: "稳定性风险"
            count: 8
            percentage: 16%
            trend: "↓ 3%（环比）"
            insight: "寻访策略优化见效，目标公司选择更精准"

        pipeline_health:
          score: 72  # 0-100
          issues:
            - "技术深度不足占比30%，需优化寻访策略"
            - "二面通过率仅40%，需优化一面筛选标准或面试官培训"

    # 工具3：人才池激活（新增）
    talent_pool_reactivation:
      input: [rejected_candidates, new_job_profile, time_elapsed]
      output:
        reactivation_candidates:
          - candidate_id: "C_010"
            name: "王五"
            previous_rejection: "薪资期望过高（期望55k，当时预算45k）"
            reactivation_reason: "新岗位预算55k，且候选人技能匹配度85%"
            suggested_approach: "主动联系，说明新岗位机会，强调预算匹配"
            message_template: "王五你好，之前聊的岗位因为预算原因没能继续，现在我们有一个高级岗位..."
            priority: "高"
```

---

### 3.4 面试协调 Agent

**现有工具**：`schedule_interview`、`notify_interviewer`、`collect_feedback`、`generate_summary`

**深度增强后**：

```yaml
# 面试协调 Agent - 深度增强版
interview_coordination_agent:
  tools:
    # 工具1：面试大纲生成（核心深度）
    generate_interview_guide:
      input: [candidate_resume, job_profile, interview_round, interviewer_profile]
      output:
        interview_guide:
          candidate_summary:
            name: "张三"
            key_experiences: ["阿里5年 Java", "主导交易系统重构", "QPS 从1K提升到10K"]
            risk_points: ["缺乏 K8s 实战经验", "无团队管理经验"]
            suggested_focus: "验证其'主导'的真实程度，考察学习能力"

          evaluation_dimensions:
            - dimension: "技术深度"
              weight: 30%
              questions:
                - question: "你提到主导了交易系统重构，能详细说说当时的架构设计吗？"
                  follow_up: 
                    - "如果当时 QPS 需要再提升10倍，你会怎么调整？"
                    - "这个过程中遇到最大的技术挑战是什么？"
                  scoring_guide:
                    - score: 5, evidence: "能清晰讲解架构演进，主动提到瓶颈和优化点"
                    - score: 3, evidence: "能描述基本流程，但对细节和取舍解释不清"
                    - score: 1, evidence: "描述模糊，明显是参与而非主导"

                - question: "你简历里提到熟悉 Spring Cloud，能说说和 Dubbo 的选型考虑吗？"
                  follow_up:
                    - "如果让你们团队现在重新选型，你会怎么建议？"
                  scoring_guide:
                    - score: 5, evidence: "能从技术、团队、业务多角度分析，有明确决策逻辑"
                    - score: 3, evidence: "能说出基本区别，但缺乏实际决策经验"

            - dimension: "项目经验"
              weight: 25%
              questions:
                - question: "你主导的交易系统重构，团队规模多大？你在其中是什么角色？"
                  red_flag_check: "若声称'主导'但团队仅2-3人，或无法描述具体分工，标记为'夸大'"

            - dimension: "学习能力"
              weight: 15%
              questions:
                - question: "你提到缺乏 K8s 实战经验，如果入职后需要负责 K8s 集群，你会怎么快速上手？"
                  scoring_guide:
                    - score: 5, evidence: "有明确学习计划，提到官方文档、实践项目、社区资源"
                    - score: 3, evidence: "提到会学习，但计划模糊"
                    - score: 1, evidence: "表示'可以学'但无具体计划，或表现出畏难情绪"

          interviewer_guidance:
            - "该候选人可能在'主导'程度上有夸大，请重点追问细节"
            - "若技术深度评分<3，建议终止面试，节省双方时间"
            - "若学习能力评分>=4，K8s 短板可接受，建议二面重点考察"

    # 工具2：面试官匹配（新增）
    match_interviewer:
      input: [candidate_skills, interview_round, available_interviewers]
      output:
        matched_interviewer:
          name: "李架构师"
          reason: "专精 Java 高并发，有交易系统经验，能深度考察候选人"
          availability: "2026-06-10 14:00-16:00"
          suggested_backup: "王架构师（K8s 专家，若一面通过，二面可匹配）"

        avoid_interviewers:
          - name: "赵经理"
            reason: "与候选人有前同事关系，可能存在偏见"

    # 工具3：面试评价收集（增强）
    collect_feedback:
      input: [interview_record, interviewer_input]
      output:
        structured_evaluation:
          dimension_scores:
            - dimension: "技术深度"
              score: 4
              evidence: "能清晰讲解架构演进，主动提到分库分表和缓存策略"
            - dimension: "项目经验"
              score: 3
              evidence: "主导程度存疑，团队规模描述前后不一致"
          red_flags:
            - "团队规模描述前后不一致（先说是5人，后说是3人）"
            - "对 K8s 的了解停留在概念层面"
          highlights:
            - "对分布式事务有深入理解，能讲清楚 TCC 和 SAGA 的区别"
          overall_recommendation: "待定"
          notes: "建议二面重点核实'主导'程度，并考察 K8s 学习能力"

        # 自动触发下一步
        next_action:
          if overall_score >= 3.5: "安排二面"
          if overall_score < 2.5: "淘汰"
          else: "待定，需补充面试"

    # 工具4：面试质量分析（新增 - 数据闭环）
    interview_quality_analysis:
      input: [interview_records, hire_outcomes]
      output:
        interviewer_effectiveness:
          - interviewer: "李架构师"
            interviews_conducted: 20
            hire_success_rate: 80%  # 其面试通过的候选人，试用期通过率
            strictness: "偏严"  # 评分普遍低于其他面试官
            bias_detected: "对非985学历候选人评分偏低"
            suggested_action: "校准评分标准，关注学历偏见"

        interview_question_effectiveness:
          - question: "交易系统重构细节"
            predictive_power: 0.75  # 该问题评分与试用期表现的相关性
            suggested_retention: "保留"
          - question: "Spring Cloud vs Dubbo"
            predictive_power: 0.30
            suggested_action: "替换为更具体的场景题"
```

---

### 3.5 薪酬谈判 Agent

**现有工具**：`check_salary_range`、`generate_offer`、`negotiate_salary`

**深度增强后**：

```yaml
# 薪酬谈判 Agent - 深度增强版
compensation_agent:
  tools:
    # 工具1：薪酬数据库查询（深度增强）
    salary_database:
      input: [job_title, level, city, industry, company_size]
      output:
        market_data:
          p25: "38k"
          p50: "45k"
          p75: "52k"
          p90: "60k"
          sample_size: 1200  # 数据来源样本量
          last_updated: "2026-05"

        company_internal_data:
          current_band: "40k-50k"
          historical_offers:
            - candidate_level: "P7 Java"
              offered: "48k"
              accepted: true
              performance_rating: "B+"  # 入职后绩效
            - candidate_level: "P7 Java"
              offered: "52k"
              accepted: true
              performance_rating: "A"  # 高薪招的人绩效更好，可支持破例
          internal_equity: "该岗位现有3人，薪资分别为42k/45k/48k，新 offer 需考虑内部公平性"

    # 工具2：谈判策略生成（核心深度）
    negotiation_strategy:
      input: [candidate_profile, market_data, company_constraints, candidate_motivation]
      output:
        candidate_motivation_analysis:
          primary_motivation: "薪资增长"  # 钱/Title/技术成长/Work-life balance/稳定性
          evidence: "期望薪资55k，当前薪资42k，涨幅要求30%"
          secondary_motivation: "技术挑战"
          evidence: "多次提到希望做'有技术难度'的项目"

        offer_package_design:
          base_salary: "48k"  # 预算上限
          sign_on_bonus: "3个月"  # 签字费，一次性，不影响长期成本
          stock_options: "0.05%"  # 期权，绑定长期
          total_first_year: "48k * 13 + 48k * 3 = 76.8万"  # 总包计算

        negotiation_tactics:
          - round: 1
            action: "先报总包，不拆分"
            message: "我们综合评估后，可以提供年薪76.8万的总包，包括月薪、签字费和期权"
            expected_response: "候选人可能会追问 base 具体多少"

          - round: 2
            action: "若候选人坚持要55k base，启动备选方案"
            alternatives:
              - "base 50k + 签字费6个月（总包更高，但 base 只涨一点）"
              - "base 48k + 提前晋升承诺（6个月后评估，若通过可涨至55k）"
              - "base 48k + 技术项目负责人 title（满足其二动机）"

        walk_away_threshold:
          base_salary: "50k"  # 超过这个数需要特批
          total_package: "80万"
          condition: "若候选人有竞品 offer 且薪资>55k，可启动特批流程"

    # 工具3：谈判模拟（新增）
    negotiation_simulator:
      input: [candidate_profile, offer_package, negotiation_history]
      output:
        simulated_scenarios:
          - scenario: "候选人说'我手里有字节 offer，base 58k'"
            probability: "30%"
            recommended_response: "强调我们的技术挑战和长期发展，同时申请特批至52k base"
            fallback: "若候选人坚持58k，建议放弃，因为会破坏内部公平性"

          - scenario: "候选人说'我对期权不感兴趣，只要现金'"
            probability: "20%"
            recommended_response: "解释期权价值（按当前估值计算），若仍不接受，可将部分期权转为签字费"

        risk_assessment:
          - "若候选人过于关注短期现金，可能稳定性风险高"
          - "若候选人接受 offer 但犹豫期>1周，可能还在等竞品 offer，需加强跟进"
```

---

### 3.6 入职跟进 Agent

**现有工具**：`send_onboarding_kit`、`schedule_first_day`、`check_progress`

**深度增强后**：

```yaml
# 入职跟进 Agent - 深度增强版
onboarding_agent:
  tools:
    # 工具1：入职准备（增强）
    prepare_onboarding:
      input: [candidate_id, job_profile, start_date]
      output:
        pre_joining_tasks:
          - task: "发送入职材料"
            deadline: "入职前7天"
            items: [offer_letter, 入职须知, 保密协议, 银行卡信息收集]

          - task: "IT 准备"
            deadline: "入职前3天"
            items: [电脑配置, 账号开通, 邮箱设置, 开发环境预装]
            note: "Java 开发需预装 JDK、IDEA、Maven、Docker"

          - task: "导师分配"
            deadline: "入职前1天"
            assigned_mentor: "王工程师"
            mentor_brief: "该候选人有高并发经验但缺乏 K8s，导师需重点帮助其上手云原生"

    # 工具2：试用期跟踪（核心深度）
    probation_tracking:
      input: [candidate_id, probation_period]
      output:
        checkin_schedule:
          - checkpoint: "30天"
            focus: "适应情况、文化融入、基础工作完成度"
            questions_for_manager:
              - "候选人是否主动融入团队？"
              - "分配的基础任务完成质量如何？"
              - "是否有明显的知识短板？"
            expected_outcomes:
              - "完成开发环境搭建"
              - "完成第一个小功能开发"
              - "参加团队周会并发言"

          - checkpoint: "90天"
            focus: "独立工作能力、技术深度验证、团队协作"
            questions_for_manager:
              - "候选人能否独立完成中等复杂度任务？"
              - "技术深度是否符合面试时的评估？"
              - "与团队成员协作是否顺畅？"
            expected_outcomes:
              - "独立完成2-3个功能模块"
              - "代码 review 通过率>80%"
              - "无严重沟通冲突"

          - checkpoint: "180天"
            focus: "综合评估、转正决策"
            questions_for_manager:
              - "候选人是否达到 P7 预期？"
              - "若转正，未来6个月的发展计划？"
              - "若淘汰，具体原因和改进建议？"
            decision_options: ["转正", "延长试用期", "淘汰"]

        early_warning_signals:
          - "30天 checkin 反馈'融入困难' → 启动文化融入支持"
          - "90天 checkin 反馈'技术深度不足' → 回溯面试评分，标记面试官校准问题"
          - "连续2次 checkin 评分<3 → 启动淘汰预警流程"

    # 工具3：招聘结果回流（核心闭环）
    feedback_loop:
      input: [hire_outcomes, original_screening_data]
      output:
        outcome_analysis:
          - candidate_id: "C_001"
            name: "张三"
            hired: true
            probation_result: "通过"
            performance_rating: "B+"
            correlation_analysis:
              - "面试评分：技术深度4/5，实际表现：B+（符合预期）"
              - "面试评分：学习能力4/5，实际表现：3个月上手 K8s（超预期）"
              - "面试风险标记：'缺乏 K8s' → 实际通过导师辅导解决"

          - candidate_id: "C_003"
            name: "赵六"
            hired: true
            probation_result: "淘汰"
            termination_reason: "技术深度不足，无法独立完成复杂任务"
            correlation_analysis:
              - "面试评分：技术深度4/5，实际表现：不达标（严重偏差）"
              - "面试问题：'交易系统重构'回答精彩，但实际是参与而非主导"
              - "根因：面试问题'主导程度'验证不足"

        system_optimization:
          - action: "更新面试大纲"
            detail: "增加'主导程度验证'问题，要求候选人画出团队分工图"
          - action: "面试官培训"
            detail: "针对'李架构师'，培训如何识别'包装型'项目经验"
          - action: "筛选标准调整"
            detail: "技术深度权重从30%提升至35%，增加代码实操环节"
          - action: "岗位画像更新"
            detail: "Java P7 画像中，增加'需提供 GitHub 代码或技术博客'作为硬性要求"
```

---

## 四、共享层深度规划

### 4.1 记忆层

**从"对话历史"到"招聘决策记忆"**：

```yaml
memory_layer:
  # 候选人关系时间线（核心）
  candidate_relationship_timeline:
    candidate_id: "C_001"
    events:
      - date: "2025-11-20"
        type: "初次接触"
        channel: "技术大会"
        content: "交换微信，候选人提到在阿里做交易系统，对高并发有兴趣"
        sentiment: "积极"

      - date: "2026-03-15"
        type: "弱联系维护"
        channel: "微信"
        content: "分享技术文章，候选人回复'感谢分享，最近在看 K8s'"
        sentiment: "中性"
        extracted_intent: "正在学习 K8s，可能考虑跳槽"

      - date: "2026-05-10"
        type: "主动求职"
        channel: "招聘网站"
        content: "候选人投递简历，期望岗位：高级 Java 工程师"
        sentiment: "积极"
        note: "与之前维护的关系一致，可加速流程"

      - date: "2026-06-01"
        type: "面试反馈"
        channel: "系统"
        content: "一面通过，技术深度评分4/5，但 K8s 仍是短板"
        action_required: "二面重点考察 K8s 学习能力"

    # 自动提醒
    upcoming_actions:
      - date: "2026-06-10"
        action: "二面安排"
        note: "已匹配 K8s 专家王架构师作为面试官"

      - date: "2026-06-20"
        action: "若二面通过，启动薪酬谈判"
        pre_work: "查询该候选人历史期望，准备谈判策略"

  # 招聘决策记忆（新增）
  hiring_decision_memory:
    job_id: "JD_001"
    decisions:
      - decision: "录用张三"
        date: "2026-06-25"
        factors:
          - "技术深度满足 P7 要求"
          - "学习能力验证通过（3个月上手 K8s）"
          - "文化匹配度85%"
          - "薪资在预算内"
        risks:
          - "K8s 实战经验不足，需导师辅导"
        mitigations:
          - "分配 K8s 专家作为导师"
          - "前3个月重点安排云原生相关任务"

        outcome: "试用期通过，绩效 B+"
        lesson: "K8s 短板可通过导师辅导解决，未来该风险可接受"
```

---

### 4.2 知识库

**从"通用 HR 知识"到"公司专属招聘标准"**：

```yaml
knowledge_base:
  # 岗位画像库（核心资产）
  job_profiles:
    Java_P7:
      title: "高级 Java 工程师"
      level: "P7"
      department: "技术部-后端架构组"

      硬性要求:
        - "本科及以上，计算机相关专业"
        - "5年以上 Java 开发经验"
        - "有高并发系统实战经验（QPS>1K）"
        - "熟悉 Spring Cloud 或 Dubbo 微服务框架"

      软性要求:
        - "能独立负责模块设计和开发"
        - "有跨团队协作经验"
        - "对技术有热情，有技术博客或开源贡献优先"

      面试考察维度:
        技术深度:
          weight: 30%
          key_questions: ["JVM 调优", "GC 算法", "分布式事务", "缓存策略"]
          must_have: "能深入讲解至少2个技术点的原理和实战经验"

        项目经验:
          weight: 25%
          must_have: "主导过至少1个中大型项目"
          red_flag: "项目描述模糊，无法说明具体职责"

        学习能力:
          weight: 15%
          must_have: "有持续学习证据（技术博客、开源、证书等）"

        文化匹配:
          weight: 15%
          company_values: ["客户第一", "拥抱变化", "团队协作"]
          red_flag: "过度自我，不配合团队"

        潜力:
          weight: 10%
          must_have: "有成长为 P8 的潜力（技术影响力、带团队潜力）"

      薪酬带宽:
        base: "40k-50k"
        total_package: "60万-80万"
        sign_on_bonus: "最多3个月"

      历史数据:
        平均招聘周期: "45天"
        试用期通过率: "85%"
        1年留存率: "90%"

  # 面试官档案（新增）
  interviewer_profiles:
    李架构师:
      name: "李 XX"
      title: "技术总监"
      expertise: ["Java 高并发", "分布式系统", "微服务架构"]
      interview_style: "偏严"
      effectiveness:
        hire_success_rate: "80%"
        predictive_power: "0.75"  # 评分与试用期表现相关性
      biases:
        - "对非985学历候选人评分偏低"
        - "对女性候选人技术能力有隐性低估"
      calibration_status: "需培训"
      suggested_training: "无意识偏见培训"

  # 招聘教训库（新增 - 最宝贵的知识）
  lessons_learned:
    - lesson_id: "LL_001"
      date: "2026-03"
      situation: "录用赵六，面试时'交易系统重构'回答精彩，但试用期发现是参与而非主导"
      root_cause: "面试问题未能有效验证'主导'程度"
      corrective_action: "更新面试大纲，增加'画出团队分工图'和'如果让你重新做，会怎么调整'等追问"
      status: "已实施"

    - lesson_id: "LL_002"
      date: "2026-05"
      situation: "3个 P7 候选人试用期技术深度不达标，面试评分均为4/5"
      root_cause: "面试官评分标准不统一，部分面试官偏松"
      corrective_action: "建立评分卡行为锚定，开展面试官校准培训"
      status: "进行中"
```

---

### 4.3 通知层

**从"任务提醒"到"招聘节奏驱动"**：

```yaml
notification_layer:
  # 招聘节奏提醒（新增）
  recruitment_rhythm_alerts:
    - trigger: "候选人3天无回复"
      action: "发送跟进提醒"
      message_template: "候选人{姓名}已3天未回复，建议通过{preferred_channel}跟进"
      escalation: "若5天仍无回复，标记为'可能流失'，启动备选候选人激活"

    - trigger: "面试后24小时未提交反馈"
      action: "催促面试官"
      message_template: "面试官{姓名}，您于{date}面试了{候选人}，请尽快提交反馈"
      escalation: "若48小时仍未提交，自动发送给面试官上级"

    - trigger: "Offer 发出后7天未接受"
      action: "风险预警"
      message_template: "候选人{姓名}的 Offer 已发出7天未接受，可能正在比较其他机会"
      suggested_action: "HR 主动联系，了解顾虑，必要时调整方案"

    - trigger: "入职前7天"
      action: "入职准备检查"
      checklist: ["IT 设备到位", "账号开通", "导师确认", "工位安排"]

    - trigger: "试用期30/90/180天"
      action: "Checkin 提醒"
      message_template: "候选人{姓名}入职已满{days}天，请安排试用期 checkin"

  # 智能通知（基于状态机）
  state_based_notifications:
    - state: "一面通过"
      notify: ["HR", "Hiring Manager", "二面面试官"]
      content: "候选人{姓名}已通过一面，技术深度评分{score}，建议二面重点考察{focus_area}"

    - state: "Offer 谈判中"
      notify: ["HR", "Hiring Manager", "财务"]
      content: "候选人{姓名}进入 Offer 谈判，期望{expected}，建议方案{suggested_package}"
```

---

### 4.4 权限层

```yaml
permission_layer:
  roles:
    HRBP:
      permissions: ["查看所有候选人", "编辑岗位画像", "发起 Offer 审批", "查看效能报表"]

    HiringManager:
      permissions: ["查看自己团队的候选人", "提交面试反馈", "审批 Offer", "查看团队招聘进度"]
      restrictions: ["不可查看薪资带宽", "不可查看其他团队候选人"]

    Interviewer:
      permissions: ["查看分配的面试任务", "提交面试反馈", "查看候选人简历"]
      restrictions: ["不可查看其他面试官反馈", "不可查看薪资信息", "不可修改岗位画像"]

    Admin:
      permissions: ["全部权限"]

  # 数据隔离规则
  data_isolation:
    - "候选人联系方式仅 HR 可见，面试官通过系统预约面试"
    - "薪资信息仅 HR 和 Hiring Manager 可见，面试官不可见"
    - "面试评价在全部轮次完成前，面试官不可查看其他面试官评价（避免偏见）"
```

---

## 五、MCP Server + 业务系统深度规划

### 5.1 MCP 工具定义

**业务逻辑封装，不仅是数据读写**：

```python
# MCP Server - 招聘业务逻辑封装
# 每个工具不是简单的 CRUD，而是封装了招聘业务规则

@mcp.tool()
def update_candidate_state(candidate_id: str, new_state: str, reason: str, operator: str):
    # 更新候选人状态 - 封装了状态机规则
    # 不是简单的 UPDATE 数据库，而是触发后续流程

    # 1. 验证状态转换是否合法
    if not state_machine.is_valid_transition(current_state, new_state):
        return {"error": f"非法状态转换：{current_state} -> {new_state}"}

    # 2. 更新数据库
    db.execute("UPDATE candidates SET state = ? WHERE id = ?", [new_state, candidate_id])

    # 3. 触发后续流程
    triggers = []
    if new_state == "初筛通过":
        triggers.append({
            "action": "自动生成面试大纲",
            "agent": "interview_coordination_agent",
            "params": {"candidate_id": candidate_id, "round": "一面"}
        })
        triggers.append({
            "action": "匹配面试官",
            "agent": "interview_coordination_agent", 
            "params": {"candidate_id": candidate_id, "round": "一面"}
        })

    elif new_state == "一面通过":
        triggers.append({
            "action": "安排二面",
            "agent": "interview_coordination_agent",
            "params": {"candidate_id": candidate_id, "round": "二面"}
        })
        triggers.append({
            "action": "通知 Hiring Manager",
            "agent": "notification_agent",
            "params": {"type": "一面通过通知", "candidate_id": candidate_id}
        })

    elif new_state == "Offer 已接受":
        triggers.append({
            "action": "启动入职准备",
            "agent": "onboarding_agent",
            "params": {"candidate_id": candidate_id}
        })
        triggers.append({
            "action": "关闭岗位（若编制已满）",
            "agent": "job_management_agent",
            "params": {"job_id": job_id}
        })

    # 4. 记录操作日志
    audit_log.record({
        "operator": operator,
        "action": "状态更新",
        "candidate_id": candidate_id,
        "from": current_state,
        "to": new_state,
        "reason": reason,
        "triggered_actions": triggers
    })

    return {
        "success": True,
        "new_state": new_state,
        "triggered_actions": triggers
    }


@mcp.tool()
def submit_interview_feedback(candidate_id: str, round: str, 
                             dimension_scores: dict, overall_recommendation: str,
                             interviewer_id: str):
    # 提交面试反馈 - 封装了评分卡规则和自动流转逻辑

    # 1. 验证评分完整性
    required_dimensions = job_profile.get_dimensions(round)
    for dim in required_dimensions:
        if dim not in dimension_scores:
            return {"error": f"缺少维度评分：{dim}"}

    # 2. 计算加权总分
    total_score = sum(
        score * job_profile.get_weight(round, dim) 
        for dim, score in dimension_scores.items()
    )

    # 3. 自动决策
    if total_score >= 4.0:
        recommendation = "通过"
        next_action = "安排下一轮面试" if round != "终面" else "进入 Offer 流程"
    elif total_score < 2.5:
        recommendation = "淘汰"
        next_action = "记录淘汰原因，更新人才池状态"
    else:
        recommendation = "待定"
        next_action = "需补充面试或多人合议"

    # 4. 存储结构化反馈
    db.execute("INSERT INTO interview_feedback (candidate_id, round, interviewer_id, dimension_scores, total_score, recommendation, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, NOW())",
               [candidate_id, round, interviewer_id, json.dumps(dimension_scores), total_score, recommendation, notes])

    # 5. 自动流转
    if recommendation == "通过" and round == "终面":
        update_candidate_state(candidate_id, "终面通过", "面试评分达标", interviewer_id)

    return {
        "success": True,
        "total_score": total_score,
        "recommendation": recommendation,
        "next_action": next_action
    }
```

---

### 5.2 数据库 Schema

**反映招聘业务实体关系**：

```sql
-- 候选人表
CREATE TABLE candidates (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(100),
    contact_info JSON,  -- 加密存储
    resume_text TEXT,
    parsed_resume JSON,  -- 结构化解析结果

    -- 招聘状态
    current_state VARCHAR(50),  -- 关联状态机
    state_history JSON,  -- 状态流转历史

    -- 匹配评分
    match_score INT,
    dimension_scores JSON,
    risk_flags JSON,

    -- 关系时间线
    relationship_timeline JSON,

    -- 招聘结果
    hired BOOLEAN DEFAULT FALSE,
    hire_date DATE,
    probation_result VARCHAR(20),  -- 通过/淘汰/进行中
    performance_rating VARCHAR(10),  -- A/B/C/D

    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- 岗位画像表
CREATE TABLE job_profiles (
    id VARCHAR(32) PRIMARY KEY,
    title VARCHAR(100),
    level VARCHAR(20),  -- P5/P6/P7
    department VARCHAR(100),

    -- 硬性要求
    hard_requirements JSON,

    -- 软性要求
    soft_requirements JSON,

    -- 面试考察维度
    evaluation_dimensions JSON,  -- [{dimension, weight, questions, scoring_guide}]

    -- 薪酬带宽
    salary_band JSON,  -- {base_min, base_max, total_min, total_max}

    -- 历史数据
    historical_metrics JSON,  -- {avg_hire_cycle, probation_pass_rate, retention_rate}

    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- 面试反馈表
CREATE TABLE interview_feedback (
    id VARCHAR(32) PRIMARY KEY,
    candidate_id VARCHAR(32),
    round VARCHAR(20),  -- 一面/二面/HR 面/终面
    interviewer_id VARCHAR(32),

    -- 结构化评分
    dimension_scores JSON,  -- {技术深度: 4, 项目经验: 3, ...}
    total_score DECIMAL(3,2),

    -- 评价内容
    red_flags JSON,
    highlights JSON,
    overall_recommendation VARCHAR(20),  -- 通过/待定/淘汰

    -- 关联岗位画像
    job_profile_id VARCHAR(32),

    created_at TIMESTAMP
);

-- 招聘效能表
CREATE TABLE recruitment_metrics (
    id VARCHAR(32) PRIMARY KEY,
    job_id VARCHAR(32),
    period VARCHAR(20),  -- 2026-Q2

    -- 漏斗指标
    funnel_metrics JSON,  -- {resume_screened, first_interview, second_interview, offer, hired}

    -- 效能指标
    otd_days INT,  -- Offer to Delivery
    probation_pass_rate DECIMAL(5,2),
    key_position_turnover_rate DECIMAL(5,2),

    -- 成本指标
    cost_per_hire DECIMAL(10,2),
    headhunter_fee_rate DECIMAL(5,2),

    created_at TIMESTAMP
);

-- 淘汰原因分析表（数据闭环核心）
CREATE TABLE rejection_analysis (
    id VARCHAR(32) PRIMARY KEY,
    candidate_id VARCHAR(32),
    rejection_reason VARCHAR(100),  -- 结构化原因
    reason_category VARCHAR(50),  -- 技术不够/稳定性/薪资/文化/其他

    -- 关联分析
    job_profile_id VARCHAR(32),
    screening_stage VARCHAR(20),  -- 初筛/一面/二面/HR 面

    -- 回流优化
    suggested_action VARCHAR(500),
    action_taken VARCHAR(500),
    action_result VARCHAR(500),

    created_at TIMESTAMP
);
```

---

## 六、实施路线图

```
Phase 1: P0 - 骨架搭建（4-6周）
  - 1.1 岗位画像模板库（5个核心岗位）
  - 1.2 面试评分卡（维度定义 + 行为锚定）
  - 1.3 淘汰原因分类体系（10个标准类别）
  - 1.4 候选人状态机（完整状态流转）
  - 1.5 基础数据表 Schema（候选人、岗位、反馈、淘汰分析）

Phase 2: P1 - 血肉填充（6-8周）
  - 2.1 简历解析风险标记（稳定性、空窗期、学历断层）
  - 2.2 岗位匹配度评分（多维度加权）
  - 2.3 面试大纲生成器（基于岗位画像 + 候选人简历）
  - 2.4 面试官匹配（专长匹配 + 回避规则）
  - 2.5 薪酬数据库（市场数据 + 内部公平性）
  - 2.6 谈判策略生成（候选人动机分析 + 方案设计）
  - 2.7 试用期跟踪（30/90/180天 checkin）
  - 2.8 关系时间线（候选人沟通历史 + 自动提醒）

Phase 3: P2 - 数据闭环（持续迭代）
  - 3.1 招聘结果回流（试用期表现 → 筛选标准优化）
  - 3.2 面试官效能分析（评分与实际表现相关性）
  - 3.3 面试问题有效性分析（预测力评估）
  - 3.4 寻访策略优化（淘汰原因分布 → 寻访条件调整）
  - 3.5 岗位画像迭代（历史数据 → 画像更新）
  - 3.6 知识库沉淀（招聘教训库 + 最佳实践）
```

---

## 七、Momus 审核修正版：把蓝图改成可交付计划

> **审核结论**：原规划方向正确，但仍偏“能力清单”，不是严格意义上的工程执行计划。最大问题不是缺想法，而是缺少依赖边界、验收口径、MVP 切片、失败退出条件和每阶段可测试产物。以下为修正版执行约束。

### 7.1 阻塞问题

| 编号 | 阻塞点 | 原因 | 修正要求 |
|---|---|---|---|
| B1 | P0/P1/P2 颗粒度过大 | “岗位画像”“状态机”“面试大纲生成器”都可拆成多个工程交付，直接开做会失控 | 每个阶段必须拆成 Schema、Service、Tool、API、UI、Test 六类产物 |
| B2 | 缺少验收标准 | 当前只说明“做什么”，没有说明“做到什么算完成” | 每个里程碑必须有可执行验收命令、样例数据和通过条件 |
| B3 | 依赖顺序不够硬 | 面试大纲依赖岗位画像和风险标记；闭环依赖结构化反馈和试用期结果 | 不满足前置条件时禁止进入下一阶段 |
| B4 | 没有 MVP 边界 | 若同时做薪酬、寻访、入职、面试官效能，会变成长期平台项目 | 第一版只做“岗位画像→简历评分→面试大纲→反馈→状态流转→淘汰原因”闭环 |
| B5 | 缺少数据质量约束 | 招聘 know-how 如果用自由文本存储，后续无法统计和优化 | 所有关键判断必须有结构化字段、证据字段、置信度字段 |
| B6 | Agent 责任边界不清 | 多个 Agent 都可能修改候选人状态，容易造成竞争和错流转 | 状态变更只能走 `update_candidate_state` 单入口，Agent 只能提交建议或调用受控工具 |

### 7.2 修正原则

1. **先结构化，再智能化**：没有岗位画像、评分卡、状态机，不做复杂 Agent 推理。
2. **先单岗位打穿，再扩岗位**：第一版只选一个核心岗位，例如 `Java_P7`。
3. **先人工可审核，再自动流转**：Agent 输出建议，系统保留人工确认点。
4. **先证据链，再结论**：所有风险、评分、淘汰、推荐都必须带 evidence。
5. **先闭环字段，再闭环分析**：没有稳定数据采集前，不做面试官效能和问题预测力分析。
6. **所有工具封装业务规则**：禁止把 MCP 工具做成裸 CRUD。

### 7.3 重排后的实施里程碑

#### M0：现状盘点与基线冻结（0.5-1 周）

**目标**：确认当前系统已有模型、API、Agent、页面，建立实施基线。

**交付物**：

- 当前能力矩阵：Candidate / Job / Application / Interview / Evaluation / Agent / MCP
- Gap 清单：已有、缺失、需增强、废弃
- 一条基准用户路径：创建岗位 → 导入候选人 → AI 初筛 → 安排面试 → 提交反馈
- 健康检查基线：`bash scripts/health-check.sh` 当前结果

**验收标准**：

- 能列出所有将被修改或复用的后端模型、API、前端页面、Agent 模块
- 明确第一版只支持一个岗位模板：`Java_P7`
- 明确哪些能力不进 MVP：薪酬数据库、完整人才地图、面试官偏见分析、自动寻访优化
- 系统健康检查结果有记录；若失败，必须标注是历史失败还是本次引入

**退出条件**：

- 无法跑通基础系统健康检查，且无法判断失败来源时，不进入 M1
- 找不到现有 Candidate / Job / Interview 基础实体时，先补基础实体，不做 Agent 深化

---

#### M1：招聘业务骨架（P0-A，1-2 周）

**目标**：把招聘专家经验落成稳定结构，而不是 prompt 文本。

**范围**：

1. 岗位画像 `job_profiles`
2. 面试评分卡 `evaluation_dimensions`
3. 淘汰原因分类 `rejection_reasons`
4. 候选人状态机 `candidate_state_machine`
5. 状态历史与审计日志

**必须交付**：

- Schema：岗位画像、评分卡、状态枚举、状态历史、淘汰原因
- Service：状态合法转换校验、评分卡读取、淘汰原因记录
- Tool：`update_candidate_state`
- API：读取岗位画像、提交状态变更、提交淘汰原因
- UI：候选人详情页展示状态、岗位画像、淘汰原因入口
- Test：状态机合法/非法转换测试、淘汰原因必填测试

**验收标准**：

- `新投递 → 初筛中 → 初筛通过 → 一面待安排` 可通过受控入口流转
- 非法转换必须被拒绝，例如 `新投递 → Offer 已发`
- 淘汰候选人必须填写结构化主原因和 evidence
- 状态变更必须写入 history/audit，不允许静默更新
- 所有状态更新只能通过统一 service/tool，不允许多个模块直接写 `current_state`

**退出条件**：

- 状态机未完成前，不允许开发面试大纲自动触发
- 淘汰原因没有结构化字段前，不允许开发淘汰原因趋势分析

---

#### M2：单岗位 MVP 智能评估（P0-B/P1-A，1-2 周）

**目标**：用 `Java_P7` 岗位打通“简历→风险→评分→建议”。

**范围**：

1. 简历风险标记：频繁跳槽、空窗期、学历/经历断层
2. 岗位匹配度评分：技术深度、项目经验、稳定性、文化匹配、潜力
3. 评分 evidence 与 gap analysis
4. 初筛建议：通过、待定、淘汰

**必须交付**：

- 风险评估 Service：输入 parsed_resume + job_profile，输出 risk_flags
- 匹配评分 Service：输出 overall_score + dimension_scores
- Agent Prompt：严格要求证据、置信度、不可臆测
- API：触发评估、查询评估结果
- UI：候选人详情页展示评分、风险、建议问题
- Test：至少 5 份固定样例简历的稳定输出测试

**验收标准**：

- 每个 risk_flag 必须包含：type、severity、evidence、suggested_question
- 每个 dimension_score 必须包含：dimension、weight、score、evidence
- 没有证据时必须输出“不确定/需核实”，禁止编造
- 同一份样例简历重复运行，关键结论保持稳定
- 评分结果可以驱动状态建议，但不能绕过人工确认直接淘汰

**退出条件**：

- 如果 Agent 输出无法稳定结构化 JSON，先修 parser/validator，不进入 M3
- 如果岗位画像字段不足以支持评分，先补画像，不写更多 prompt

---

#### M3：面试大纲与结构化反馈（P1-B，1-2 周）

**目标**：把初筛结论转化为可执行面试动作，并收集可回流数据。

**范围**：

1. 面试大纲生成
2. 面试官提示
3. 结构化面试反馈
4. 面试结果驱动状态建议

**必须交付**：

- Tool：`generate_interview_guide`
- Tool：`submit_interview_feedback`
- API：生成面试大纲、提交反馈
- UI：面试大纲页、结构化反馈表单
- Test：大纲生成包含风险追问；反馈缺维度时拒绝提交

**验收标准**：

- 面试大纲必须引用候选人简历证据和岗位画像要求
- 每个问题必须绑定考察维度和评分锚定
- 风险点必须转成追问，例如“主导程度存疑→要求画团队分工图”
- 面试反馈必须包含维度评分、evidence、red_flags/highlights、overall_recommendation
- 面试结果只产生下一步建议；真正状态流转仍走 `update_candidate_state`

**退出条件**：

- 结构化反馈未落库前，不做面试官效能分析
- 面试大纲无法追溯到岗位画像和简历证据时，不允许上线

---

#### M4：最小闭环（P1-C，1 周）

**目标**：完成第一条招聘业务闭环，不做高级分析。

**闭环路径**：

```text
岗位画像 → 简历评估 → 风险标记 → 面试大纲 → 面试反馈 → 状态流转 → 淘汰原因/通过原因记录
```

**必须交付**：

- 通过原因/淘汰原因统一记录
- 候选人详情页能看到完整决策链
- Dashboard 最小漏斗：初筛数、初筛通过、一面、Offer、淘汰原因分布
- Mock E2E：覆盖上述闭环路径
- 真实后端健康检查：必须按项目 SOP 跑 `bash scripts/health-check.sh`

**验收标准**：

- 任一候选人的状态、评分、面试反馈、淘汰/通过原因可追溯
- Dashboard 指标来自真实结构化字段，不从自由文本解析
- Mock E2E 通过不代表完成，必须真实后端健康检查通过
- 健康检查 6/6 pass 才算 M4 完成

**退出条件**：

- 若真实登录或真实后端不可用，不能宣称闭环完成
- 若 Dashboard 指标无法追溯到结构化字段，不能进入 P2 分析

---

#### M5：P2 数据闭环分析（持续迭代）

**进入条件**：至少积累 20 条结构化候选人记录、10 条面试反馈、5 条明确淘汰/通过原因。

**范围**：

- 招聘结果回流
- 面试官效能分析
- 面试问题有效性分析
- 寻访策略优化建议
- 岗位画像迭代建议
- 招聘教训库

**验收标准**：

- 每条优化建议必须能追溯到具体数据样本
- 样本不足时必须显示“数据不足”，禁止强行给结论
- 画像更新必须走人工确认，不允许自动覆盖核心岗位标准
- 面试官效能只做内部校准，不直接作为惩罚性指标

**退出条件**：

- 样本不足时只展示数据采集状态，不展示趋势判断
- 数据质量字段缺失率 > 20% 时，暂停分析，先修采集链路

### 7.4 第一版 MVP 明确范围

**必须做**：

```text
Java_P7 岗位画像
状态机
结构化淘汰原因
简历风险标记
岗位匹配评分
面试大纲生成
结构化反馈
候选人决策链展示
最小 Dashboard
系统健康检查
```

**明确不做**：

```text
完整薪酬数据库
自动谈判 Agent
完整人才地图
外部招聘网站自动寻访
面试官偏见自动判定
试用期 180 天真实闭环
多岗位模板批量扩展
自动修改岗位画像
```

### 7.5 全局验收清单

每个阶段结束必须满足：

1. **Schema 可迁移**：Alembic migration 可升级，字段命名稳定。
2. **Service 可测**：核心业务规则有单元测试。
3. **Tool 受控**：MCP 工具封装业务规则，不暴露裸写库能力。
4. **API 可用**：关键接口有正常、异常、权限场景测试。
5. **UI 可操作**：不是只展示数据，必须能完成对应业务动作。
6. **Agent 可回退**：LLM 不可用时，系统仍能展示基础数据和人工操作入口。
7. **证据可追溯**：任何评分、风险、淘汰、推荐都有 evidence。
8. **健康检查通过**：代码改动后必须跑 `bash scripts/health-check.sh`，按项目要求 6/6 pass。

### 7.6 风险与控制

| 风险 | 表现 | 控制方式 |
|---|---|---|
| Prompt 先行导致不可测 | 输出漂亮但无法统计 | 所有 Agent 输出必须先过 Pydantic/JSON Schema 校验 |
| 状态流转混乱 | 多 Agent 同时改候选人状态 | 状态变更统一入口 + audit log + 乐观锁 |
| 过早做闭环分析 | 样本不足但给出趋势 | 设置最小样本门槛，不足只展示数据采集进度 |
| 招聘经验变成自由文本 | 后续无法复盘 | 关键字段枚举化，文本只作为 evidence/notes |
| MVP 膨胀 | 同时做寻访、薪酬、入职 | 严格按 M1-M4 关闭第一条链路后再扩展 |
| 健康检查被忽略 | 前端 mock 通过但真实系统不可用 | 每次代码变更后强制跑 `scripts/health-check.sh` |

### 7.7 最终通过定义

第一阶段真正完成的定义不是“功能都写了”，而是：

```text
一个 Java_P7 候选人从导入到初筛、面试大纲、结构化反馈、状态流转、淘汰/通过原因沉淀，全链路可操作、可追溯、可测试、真实后端可用。
```

只有达到这个标准，才进入薪酬谈判、关系维护、试用期跟踪、面试官效能等高级能力。

---

## 总结

> **你的架构有"深度"的容器，现在这份规划就是往容器里注入"血肉"的完整蓝图。**

核心原则：

1. **不是让大模型"更聪明"，而是让系统"更懂招聘"**——把你知道的但大模型不知道的，编码进去
2. **每个 Agent 的工具不是通用 CRUD，而是封装了招聘业务规则**——状态流转、评分卡、风险标记、谈判策略
3. **数据必须闭环**——每次招聘的结果（录用/淘汰/试用期表现）都要回流，持续优化前面的环节
4. **知识库是核心资产**——岗位画像、面试官档案、招聘教训，这些是大模型永远学不到的

这份规划如果全部落地，你的 AI 招聘 Agent 就从 **"L2 流程封装"** 跃升到 **"L3 行业 Know-how 注入"**，并且有清晰的路径通往 **"L4 数据闭环沉淀"**。
