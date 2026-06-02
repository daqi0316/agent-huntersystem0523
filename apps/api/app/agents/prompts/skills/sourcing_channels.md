# skill: sourcing_channels — 招聘渠道策略手册

> 本文件是 LLM 工具化技能，按需通过 `load_skill(name="sourcing_channels")` 加载。
> 内容与 Agent Prompt **不重复**，专注渠道选择逻辑和操作方法。

## 1. 渠道效果矩阵（按岗位类型）

| 渠道 | 研发/技术 | 产品/设计 | 销售/市场 | 运营 | 校招 | 实习 |
|------|-----------|-----------|-----------|------|------|------|
| Boss直聘 | ★★★★ | ★★★★ | ★★★★★ | ★★★★ | ★★ | ★★★ |
| 猎聘 | ★★★★ | ★★★ | ★★★ | ★★ | ★ | ★ |
| LinkedIn | ★★★ | ★★★★ | ★★★★ | ★★★ | ★★ | ★★ |
| 脉脉 | ★★★ | ★★★ | ★★★ | ★★★ | ★ | ★ |
| 拉勾 | ★★★★ | ★★★ | ★★ | ★★ | ★★ | ★★ |
| 智联/前程 | ★★ | ★★ | ★★★ | ★★★★ | ★★★ | ★★★ |
| 内部推荐 | ★★★★★ | ★★★★★ | ★★★★ | ★★★★ | ★★ | ★★ |
| GitHub Jobs | ★★★ | ★ | ★ | ★ | ★ | ★ |
| V2EX | ★★★ | ★★ | ★ | ★ | ★★ | ★ |

## 2. 渠道成本-质量分析

| 渠道 | 平均成本/候选人 | 面试通过率 | 入职率 | 适合场景 |
|------|----------------|-----------|--------|---------|
| 内部推荐 | ¥500-2000 | 45% | 85% | 高质量刚需岗位 |
| 猎聘 | ¥5000-15000 | 25% | 65% | 中高端（年薪 30W+）|
| Boss直聘 | ¥500-2000 | 20% | 50% | 量大、中低端 |
| LinkedIn | ¥3000-8000 | 30% | 60% | 国际化/外企背景 |
| 拉勾 | ¥1000-3000 | 22% | 55% | 互联网背景 |
| 校招官网 | ¥0 | 15% | 70% | 批量校招 |
| 实习生平台 | ¥0-500 | 10% | 60% | 实习/初级岗 |

## 3. Boolean Search 模板

### 3.1 研发/技术岗
```
# Python后端（通用）
(python OR django OR fastapi OR flask) AND (postgresql OR mysql OR redis)
AND ("5年" OR "5+年" OR "senior" OR "资深")
NOT (intern OR 实习 OR junior)

# 前端
(javascript OR typescript OR react OR vue OR angular)
AND ("5年" OR "senior" OR "资深")
AND (frontend OR 前端)
NOT (intern)

# 数据/算法
(python OR scala) AND (machine learning OR ml OR data science OR 数据科学)
AND (sql OR spark OR hive OR kafka)
NOT (intern)

# DevOps/SRE
(aws OR azure OR gcp) AND (kubernetes OR k8s OR docker OR terraform)
AND (ci/cd OR jenkins OR github actions)
NOT (intern)
```

### 3.2 产品/运营岗
```
# 产品经理
(product manager OR pm OR 产品经理) AND ("3年" OR "5年" OR senior)
AND (b2b OR b2c OR saas OR to B)
NOT (intern OR 实习)

# 运营
(运营 OR operations) AND (用户运营 OR 内容运营 OR 活动运营)
AND ("2年" OR "3年")
```

### 3.3 简历搜索技巧
| 技巧 | 示例 |
|------|------|
| 精确短语 | `"机器学习" AND "推荐系统"` |
| 同义词扩展 | `(agile OR scrum OR 敏捷)` |
| 排除词 | `NOT (intern OR 实习 OR junior)` |
| 时间限定 | `After:2020-01-01` |
| 地点限定 | `location:北京 AND (阿里 OR 字节 OR 腾讯)` |

## 4. 渠道时效性规律

| 渠道 | 发布后黄金期 | 建议刷新策略 |
|------|-------------|-------------|
| Boss直聘 | 3天内 | 每天 10:00 / 14:00 刷新 |
| 拉勾 | 5天内 | 每2天刷新 |
| 猎聘 | 7天内 | 每周刷新 |
| LinkedIn | 14天内 | 每周更新一次 |
| 内部推荐 | 开放期内持续有效 | 定期提醒 |

**最佳沟通时间**（候选人端）：
- Boss直聘：候选人活跃高峰 12:00-13:00 / 20:00-22:00
- 脉脉：工作日 8:00-9:00（通勤浏览）
- LinkedIn：工作日 9:00-10:00 / 18:00-19:00

## 5. 渠道选择决策树

```
输入：岗位类型、职级、紧急度、预算

1. 年薪 ≥ 50W 的Senior+岗位？
   → YES：猎聘（主动猎头）+ LinkedIn + 内部推荐
   → NO：继续

2. 是技术研发岗？
   → YES：GitHub + V2EX + 内部推荐 + Boss直聘
   → NO：继续

3. 预算 < ¥5000？
   → YES：内部推荐 + Boss直聘 + 拉勾
   → NO：继续

4. 需要 5 人以上批量招聘？
   → YES：校招官网 + 实习生平台 + Boss直聘
   → NO：继续

5. 默认组合：Boss直聘 + 拉勾 + 内部推荐
```

## 6. 候选人来源追踪

每份简历记录来源标签：
```python
SOURCE_TAGS = {
    "boss": "boss_direct",
    "boss_referral": "boss_referral",  # Boss内推
    "lagou": "lagou",
    "liepin": "liepin",
    "linkedin": "linkedin",
    "wechat": "wechat_sourcing",
    "internal_referral": "internal_referral",
    "campus": "campus",
    "github": "github",
    "v2ex": "v2ex",
    "other": "other"
}
```

**ROI 计算**：
```
cost_per_hire = sum(channel_costs) / hired_from_channel
time_to_hire_by_channel = avg_days_to_offer(channel)
quality_score_by_channel = avg_90day_retention(channel)
```

## 7. 冷启动策略（无简历库时）

| 天数 | 动作 | 目标 |
|------|------|------|
| Day 1 | 在 Boss/拉勾/猎聘发布 JD（精准关键词）| 收集首批简历 |
| Day 2-3 | Boolean 搜索主动下载简历 | 50 份技术岗 |
| Day 3 | 启动内部推荐（奖励政策通知）| 动员内推 |
| Day 5 | LinkedIn InMail 主动联系 | 20 人触达 |
| Day 7 | 复盘渠道效果，调整预算分配 | 聚焦高转化渠道 |
