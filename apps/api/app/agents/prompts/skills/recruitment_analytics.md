# skill: recruitment_analytics — 招聘指标与 SQL 查询手册

> 本文件是 LLM 工具化技能，按需通过 `load_skill(name="recruitment_analytics")` 加载。
> 内容与 Agent Prompt **不重复**，专注 KPI 定义和数据查询模板。

## 1. 核心指标体系

### 1.1 效率指标
| 指标 | 定义 | 计算公式 | 行业基准 |
|------|------|---------|---------|
| Time-to-Hire (TTH) | 从职位开放到 offer 接受的天数 | `offer_accepted_date - job_open_date` | 研发：30-45天；其他：20-30天 |
| Time-to-Interview | 从投递到首次面试 | `first_interview_date - application_date` | < 7 天 |
| Time-to-Reject | 从投递到拒信 | `rejection_date - application_date` | < 14 天 |
| Offer Acceptance Rate | offer 接受率 | `accepted_offers / total_offers * 100%` | 75-85% |

### 1.2 质量指标
| 指标 | 定义 | 计算公式 | 目标 |
|------|------|---------|------|
| Quality-of-Hire | 入职后 6 个月绩效 | `avg(performance_score) at 6-month` | ≥ 3.5/5.0 |
| New Hire Retention | 一年留存率 | `retained_12m / total_hired_12m` | ≥ 80% |
| 90-day Failure Rate | 90天内离职率 | `resigned_within_90d / total_started` | < 10% |
| Manager Satisfaction | 招聘满意度 | survey score (1-5) | ≥ 4.0 |

### 1.3 成本指标
| 指标 | 定义 | 计算公式 |
|------|------|---------|
| Cost-per-Hire (CPH) | 每 hire 平均成本 | `total_recruitment_cost / total_hires` |
| Cost-per-Interview | 每次面试成本 | `total_cost / total_interviews` |
| Cost-per-Reject | 每个 reject 成本 | `total_cost / total_rejects` |
| Recruitment ROI | 招聘投资回报 | `(estimated_productivity_gain - total_cost) / total_cost` |

## 2. SQL 查询模板

### 2.1 招聘漏斗分析（Funnel）
```sql
SELECT
    job_id,
    job_title,
    COUNT(DISTINCT application_id) AS total_applications,
    COUNT(DISTINCT CASE WHEN stage >= 'screening' THEN application_id END) AS screened,
    COUNT(DISTINCT CASE WHEN stage >= 'interview' THEN application_id END) AS interviewed,
    COUNT(DISTINCT CASE WHEN stage >= 'offer' THEN application_id END) AS offered,
    COUNT(DISTINCT CASE WHEN stage = 'hired' THEN application_id END) AS hired,
    -- 转化率
    ROUND(COUNT(DISTINCT CASE WHEN stage >= 'screening' THEN application_id END) * 100.0
        / NULLIF(COUNT(DISTINCT application_id), 0), 1) AS screening_rate,
    ROUND(COUNT(DISTINCT CASE WHEN stage >= 'interview' THEN application_id END) * 100.0
        / NULLIF(COUNT(DISTINCT CASE WHEN stage >= 'screening' THEN application_id END), 0), 1) AS interview_rate,
    ROUND(COUNT(DISTINCT CASE WHEN stage >= 'offer' THEN application_id END) * 100.0
        / NULLIF(COUNT(DISTINCT CASE WHEN stage >= 'interview' THEN application_id END), 0), 1) AS offer_rate,
    ROUND(COUNT(DISTINCT CASE WHEN stage = 'hired' THEN application_id END) * 100.0
        / NULLIF(COUNT(DISTINCT CASE WHEN stage >= 'offer' THEN application_id END), 0), 1) AS acceptance_rate
FROM recruitment_funnel
WHERE job_open_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '3 months')
GROUP BY job_id, job_title
ORDER BY job_open_date DESC;
```

### 2.2 Time-to-Hire 按渠道分析
```sql
SELECT
    source,
    COUNT(*) AS total_hires,
    AVG(EXTRACT(DAY FROM offer_accepted_date - job_open_date)) AS avg_tth_days,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(DAY FROM offer_accepted_date - job_open_date)) AS median_tth_days,
    PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY EXTRACT(DAY FROM offer_accepted_date - job_open_date)) AS p90_tth_days
FROM hires h
JOIN jobs j ON h.job_id = j.id
WHERE hire_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '6 months')
GROUP BY source
ORDER BY total_hires DESC;
```

### 2.3 渠道 ROI 分析
```sql
WITH channel_costs AS (
    SELECT
        source,
        SUM(channel_cost) AS total_cost
    FROM recruitment_expenses
    WHERE expense_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '6 months')
    GROUP BY source
),
channel_hires AS (
    SELECT
        source,
        COUNT(*) AS hires,
        AVG(base_salary) AS avg_salary
    FROM hires
    WHERE hire_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '6 months')
    GROUP BY source
)
SELECT
    c.source,
    COALESCE(h.hires, 0) AS hires,
    COALESCE(c.total_cost, 0) AS total_cost,
    ROUND(COALESCE(c.total_cost, 0) * 1.0 / NULLIF(h.hires, 0), 2) AS cost_per_hire,
    ROUND(COALESCE(h.avg_salary, 0) * 0.15 / NULLIF(COALESCE(c.total_cost, 0), 0), 2) AS roi_estimate
FROM channel_costs c
LEFT JOIN channel_hires h ON c.source = h.source
ORDER BY cost_per_hire ASC;
```

### 2.4 招聘质量追踪（90-day retention）
```sql
SELECT
    job_family,
    COUNT(DISTINCT hired_id) AS total_hired,
    COUNT(DISTINCT CASE WHEN resignation_date <= hire_date + INTERVAL '90 days' THEN hired_id END) AS failed_90d,
    ROUND(COUNT(DISTINCT CASE WHEN resignation_date > hire_date + INTERVAL '90 days' OR resignation_date IS NULL THEN hired_id END) * 100.0
        / NULLIF(COUNT(DISTINCT hired_id), 0), 1) AS retention_rate_90d,
    AVG(CASE WHEN performance_score IS NOT NULL THEN performance_score END) AS avg_perf_score
FROM hire_outcomes ho
JOIN jobs j ON ho.job_id = j.id
WHERE hire_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '12 months')
GROUP BY job_family
ORDER BY retention_rate_90d ASC;
```

## 3. 报告模板

### 3.1 月度招聘报告结构
```
1. 执行摘要（1页）
   - 本月 hires vs 目标
   - 关键亮点 / 风险

2. 招聘漏斗（按职位类别）
   - 申请 → 面试 → Offer → 入职 转化率
   - 与上月对比

3. 渠道表现
   - 各渠道 CPH 和质量
   - Top performing channels

4. Time-to-Hire 趋势
   - 按职位类别 / 渠道
   - 与行业基准对比

5. 质量追踪
   - 90-day retention
   - Manager satisfaction score

6. 下月预测
   - Open positions 预计关闭时间
   - Pipeline 充足度
```

## 4. 预警阈值

| 指标 | 绿色 | 黄色 | 红色 |
|------|------|------|------|
| TTH（研发）| < 35 天 | 35-50 天 | > 50 天 |
| Offer Acceptance Rate | > 80% | 60-80% | < 60% |
| 90-day Retention | > 90% | 80-90% | < 80% |
| Interview-to-Hire Ratio | < 15 | 15-25 | > 25 |
| CPH vs Budget | < 100% | 100-120% | > 120% |
| Active Pipeline Coverage | > 3x open reqs | 2-3x | < 2x |
