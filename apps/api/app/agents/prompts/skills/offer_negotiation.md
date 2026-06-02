# skill: offer_negotiation — Offer 谈判策略手册

> 本文件是 LLM 工具化技能，按需通过 `load_skill(name="offer_negotiation")` 加载。
> 内容与 Agent Prompt **不重复**，专注谈判策略和薪酬结构分析。

## 1. 薪酬结构解析

### 1.1 完整薪酬包组件
| 组件 | 说明 | 谈判难度 |
|------|------|---------|
| Base Salary | 年固定现金 | 中（公司有 band 限制）|
| Annual Bonus | 年终奖（通常 0-30%）| 低（有浮动空间）|
| Signing Bonus | 签约现金（一次性）| 高（纯现金，灵活）|
| Equity / RSUs | 股票/期权 | 中（ VestingSchedule 影响）|
| Benefits | 保险/补贴/假期 | 低（公司标准化）|

### 1.2 市场基准对比
```python
def calculate_market_position(candidate_salary: int, role_band: dict, market_data: dict) -> str:
    """计算候选人在市场中的位置"""
    p25 = market_data["p25"]
    p50 = market_data["p50"]
    p75 = market_data["p75"]

    if candidate_salary < p25:
        return "低于市场，建议调整至 p50"
    elif candidate_salary < p50:
        return "略低于市场，可适当上调"
    elif candidate_salary < p75:
        return "市场中等，可接受"
    else:
        return "高于市场，需要特殊审批"
```

## 2. 候选人类型与策略

### 2.1 有现有 Offer 的候选人
```
信号：
- 明确说有竞品 offer（有时间压力）
- 表达"已经在走流程"

策略：
1. 不要贬低竞品（显得不专业）
2. 了解对方 offer 结构后对比
3. 说明我们 offer 的独特优势（非现金福利/成长空间/稳定性）
4. 签约奖金可以弥补 base 差距
5. 给出明确 deadline（合理，如 3-5 天）

话术：
"我们非常希望你能加入团队。你提到有其他 offer，这是对你的认可。
  我们能了解对方的 offer 结构吗？我们可以看看能不能给你一个更有竞争力的方案。"
```

### 2.2 薪资期望明显高于我们 band 的候选人
```
信号：
- 期望 > 我们岗位 band 上限 30%+
- 明确说低于 X 不考虑

策略：
1. 诚实说明我们的 band 限制（展现诚信）
2. 拆分 offer 结构，看看有没有其他弹性部分
3. 讨论未来晋升路径和时间线（"加入后 12 个月可以重新 review"）
4. 如果确实差太多，诚实告知，避免浪费双方时间

话术：
"你的期望我们非常理解。对于这个 level，我们的 base 范围是 A-B。
  超出这个范围需要 VP special approval，周期较长且不确定。
  我们可以在 signing bonus 上做一些补偿，你看这样可以吗？"
```

### 2.3 犹豫不决的候选人
```
信号：
- 表达"需要再考虑一下"
- 不给明确回复时间
- 反复问相同问题

策略：
1. 了解犹豫的真实原因（钱？角色？团队？）
2. 针对性解决（不是所有问题都能解决，要诚实）
3. 避免过度催促（适得其反）
4. 可以给一个"最后一次回复"的 deadline

话术：
"我理解这个决定对你很重要。我们希望你能加入，但也不想给你太大压力。
  你最关心的是什么？是薪资、发展还是团队方向？我们可以聊聊。"
```

## 3. 常用谈判筹码

| 筹码 | 适用场景 | 使用注意 |
|------|---------|---------|
| 签约奖金 | base 有 band 上限 | 一次性，不影响长期成本 |
| 额外假期 | base 难调时 | 成本低，候选人感知价值高 |
| 弹性工作 | 无法加薪时 | 明确是每周几天还是完全弹性 |
| 股权 | 长期留人 | 说明 vesting schedule |
| 职位 title | 钱达不到时 | 不轻易给，除非真的合适 |
| 项目/团队选择 | 技术负责人/架构师岗 | 说明可选范围 |
| 签字确认 | 候选人犹豫时 | 不要虚报，要实事求是 |

## 4. 常见拒绝理由与应对

| 拒绝理由 | 真实原因 | 建议应对 |
|---------|---------|---------|
| "等另一个 offer 结果" | 比较中 | 了解对方 offer 结构；说明我们独特优势；给合理 deadline |
| "薪资不够" | 钱是核心 | 尽可能补 signing bonus；说明 total compensation |
| "觉得岗位不够高级" | 自我认知偏差或信息不足 | 详细说明职责范围和成长空间 |
| "想留在现公司" | 现状足够好或害怕变化 | 不强求，但了解障碍（也许可以解决）|
| "通勤太远" | 现实因素 | 讨论远程选项或 relocation 支持 |
| "家人不同意" | 非理性因素 | 了解详情，也许有解决方案 |

## 5. 内部审批流程

```
Level 1：HR 自行决定（无需 escalation）
  - Base 在 band 内
  - Total package 差距 < 10%

Level 2：HR Manager 审批（24h）
  - Base 超出 band 10% 以内
  - 需要 signing bonus 补差

Level 3：VP 审批（48-72h）
  - Base 超出 band 20%+
  - 或需要特殊 equity grant

Level 4：CXO 审批（5 天+）
  - 超市场 75% 分位
  - 极其稀缺人才
```

## 6. 谈判红线

| 红线 | 说明 |
|------|------|
| 不虚报 offer | 永远不要夸大我们的 offer 内容 |
| 不贬低竞品 | 不要说"那家公司不好" |
| 不承诺无法兑现的事 | 例如"半年后肯定晋升" |
| 不在最后一刻改变条件 | 会严重损害信任 |
| 钱不是唯一解 | 其他筹码（假期、弹性、项目）往往更有效 |

## 7. 谈完后记录模板

```json
{
  "candidate_id": "xxx",
  "original_offer": {"base": 400000, "bonus": "15%", "signing": 0, "equity": 0},
  "negotiated_offer": {"base": 420000, "bonus": "15%", "signing": 50000, "equity": 0},
  "negotiation_rounds": 2,
  "key_concerns_addressed": ["职业发展", "团队方向"],
  "concessions_made": ["signing bonus 5万"],
  "accepted": true,
  "time_to_decision": "3 days"
}
```
