# skill: resume_parser — 简历解析参考手册

> 本文件是 LLM 工具化技能，按需通过 `load_skill(name="resume_parser")` 加载。
> 内容与 `screening.md` / `interview.md` 等 Agent Prompt **不重复**，专注解析域知识。

## 1. 段落结构识别

| 段落关键词 | 标准含义 |
|-----------|---------|
| `工作经历` / `Experience` / `职业履历` | 工作经历主体 |
| `教育背景` / `Education` | 教育经历 |
| `项目经历` / `Project` / `项目经验` | 项目经历（可与工作经历合并）|
| `技能特长` / `Skills` / `技术栈` | 技能列表 |
| `自我评价` / `Summary` / `About` | 自我描述（参考价值低） |

**通用规则**：
- 标题行不参与内容解析，仅作分段标记
- 内容为空行时重新分段
- 同级标题下第一个非空段落为该 section body

## 2. 时间线解析

**格式容忍**（按优先级匹配）：
```
YYYY.MM - YYYY.MM   # 2019.07 - 2022.03
YYYY/MM - YYYY/MM   # 2019/07 - 2022/03
YYYY-MM - YYYY-MM   # 2019-07 - 2022-03
YYYY年MM月 - YYYY年MM月  # 2019年7月 - 2022年3月
YYYY.MM - 至今      # 2019.07 - 至今
YYYY/MM - Now       # 2019/07 - Now
```

**空档检测**（超过 6 个月需标记）：
```python
def detect_gaps(positions: list[dict]) -> list[dict]:
    gaps = []
    sorted_pos = sorted(positions, key=lambda p: p["start"])
    for i in range(len(sorted_pos) - 1):
        gap_months = months_between(sorted_pos[i]["end"], sorted_pos[i+1]["start"])
        if gap_months > 6:
            gaps.append({"from": sorted_pos[i]["end"], "to": sorted_pos[i+1]["start"], "months": gap_months})
    return gaps
```

## 3. 技能标准化

**技能层级映射**（招聘场景）：
```
L1 入门  — 了解概念，能做练习项目
L2 初级  — 能在指导下完成工作，独立操作有限
L3 中级  — 独立完成，熟练，有独立解决问题能力
L4 高级  — 精通原理，能指导他人，架构设计能力
L5 专家  — 行业顶尖，定义技术方向
```

**常见技能别名**（去重）：
| 别名 | 标准名 |
|------|--------|
| Python3 / python3 / py | Python |
| JS / es6 / ECMAScript6 | JavaScript |
| TS / TypeScript4 / ts4 | TypeScript |
| PG / postgres / pgsql | PostgreSQL |
| K8s / k8s / kubernetes | Kubernetes |
| Vue2 / vue.js 2.x | Vue.js |
| React17 / React 17 / rc17 | React |

## 4. 教育信息解析

| 字段 | 提取规则 |
|------|---------|
| 学校 | 取前 20 字，去除"大学"等通用后缀后匹配高校库 |
| 学历 | 匹配：博士 / 硕士 / 本科 / 学士 / 大专 / 高中 / 中专 |
| 专业 | 取"计算机"前后的专业名词；MBA 归类为管理学 |
| 时间 | 同时间线解析规则 |

**高校识别**（国内）：前缀在 300 所重点高校名单内 → 标记为 985/211。

## 5. 薪资信息提取（可选）

| 格式 | 解析规则 |
|------|---------|
| `20-30K` / `20k-30k` | 月薪区间，×12 → 年薪 |
| `30万年薪` / `30W/年` | 直接年薪资 |
| `面议` / `Negotiable` | 无法提取 |
| `15k*14` | 月薪 × 14 个月 |

## 6. 输出 Schema

```json
{
  "name": "姓名",
  "latest_title": "最近职位",
  "total_years": 5.5,
  "education": [
    {"school": "学校名", "degree": "硕士", "major": "计算机科学", "grad_year": 2019}
  ],
  "skills": [
    {"name": "Python", "level": "L3", "duration_years": 4},
    {"name": "PostgreSQL", "level": "L3", "duration_years": 3}
  ],
  "positions": [
    {
      "company": "公司名",
      "title": "职位名",
      "start": "2019.07",
      "end": "2022.03",
      "description": "工作描述（脱敏后）",
      "highlights": ["量化成果1", "量化成果2"]
    }
  ],
  "gaps": [
    {"from": "2022.03", "to": "2022.10", "months": 7}
  ],
  "salary_estimate": {"min_annual": 300000, "max_annual": 450000, "currency": "CNY"},
  "parsed_warnings": ["教育经历时间存疑", "技能描述过长"]
}
```

## 7. 风险信号（标记 red_flag）

| 信号 | 阈值 |
|------|------|
| 频繁跳槽 | 3 年内换 3+ 工作，每段 < 8 个月 |
| 空档期 | 超过 12 个月未就业 |
| 技能夸大 | 同技能描述中同时出现 L2 和 L5 |
| 薪资异常 | 市场最低 25% 以下（需市场基准） |
| 学历断层 | 工作 5 年以上但无学历信息 |
