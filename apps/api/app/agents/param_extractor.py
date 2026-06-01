"""NL参数提取 — 从自然语言中抽取 Agent 所需的 action/entities。

RouterAgent 在 dispatch 给 Specialist Agent 前调用 extract_params()
将 input_data 从 {"text": "..."} 扩展为 {"text": "...", "action": "...", "target_companies": [...], ...}。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Action Keyword Rules ──
# (keywords, intent_filter, action)
# intent_filter="" means match any intent
_ACTION_RULES: list[tuple[list[str], str, str]] = [
    # sourcing
    (["mapping", "人才地图", "人才mapping", "竞品", "目标公司", "对标"], "sourcing", "talent_map"),
    (["搜一下", "搜索候选人", "找候选人", "人才搜索", "找人", "看看候选人", "查一下"], "sourcing", "candidate_search"),
    (["话术", "触达", "沟通模板", "挖人", "联系他", "联系她"], "sourcing", "outreach"),
    (["渠道", "渠道策略", "投放", "预算分配", "渠道推荐"], "sourcing", "channel_strategy"),
    # screening
    (["批量", "批量筛选", "批量初筛", "多个人"], "screening", "batch"),
    (["多维", "多维评估", "多维度", "六个维度"], "screening", "evaluate"),
    # interview
    (["评价表", "评估表", "生成评价"], "interview", "evaluation_form"),
    (["反馈汇总", "汇总反馈", "汇总评价"], "interview", "summarize_feedback"),
    (["提醒", "面试提醒", "通知"], "interview", "reminder"),
    # offering
    (["基准", "市场薪酬", "薪酬基准", "薪资基准", "市场水平"], "offering", "benchmark"),
    (["总包", "计算总包", "计算薪酬", "算薪资", "算总包"], "offering", "calculate"),
    (["offer函", "offer信", "录用函", "录用信", "offer letter"], "offering", "offer_letter"),
    (["谈判", "谈判策略", "谈薪策略", "话术建议"], "offering", "negotiation"),
    (["风险评估", "offer风险", "录用风险"], "offering", "risk_assessment"),
    # onboarding
    (["转正", "转正评估", "试用期评估", "转正评审"], "onboarding", "probation_review"),
    (["里程碑", "更新里程碑", "修改里程碑"], "onboarding", "update_milestone"),
    # analytics
    (["漏斗", "转化率", "招聘漏斗"], "analytics", "funnel"),
    (["渠道效果", "渠道分析", "渠道ROI"], "analytics", "channels"),
    (["kpi", "招聘KPI", "关键指标"], "analytics", "kpi"),
    (["异常", "异常检测", "告警", "数据异常"], "analytics", "anomalies"),
    (["报告", "全量报告", "招聘报告", "完整报告"], "analytics", "report"),
]

# Intent → default action mapping (used when no action keyword is matched)
_INTENT_DEFAULT_ACTION: dict[str, str] = {
    "screening": "screen",
    "interview": "schedule",
    "jd_generation": "jd_generation",
    "candidate_search": "candidate_search",
    "outreach": "outreach",
    "channel_strategy": "channel_strategy",
    "offering": "calculate",
    "onboarding": "plan",
    "analytics": "funnel",
    "report": "report",
    "knowledge_query": "query",
    "settings": "settings",
    "chat": "chat",
}

# ── Known Entities (longer-first for greedy match) ──

_COMPANIES = sorted([
    "字节跳动", "字节", "阿里巴巴", "阿里", "腾讯", "百度", "美团",
    "小红书", "拼多多", "京东", "蚂蚁集团", "蚂蚁金服", "蚂蚁",
    "微软", "谷歌", "Google", "Amazon", "亚马逊", "Apple", "苹果",
    "Meta", "大疆", "DJI", "华为", "小米", "快手", "滴滴", "网易",
    "B站", "bilibili", "哔哩哔哩", "理想汽车", "蔚来", "小鹏",
    "特斯拉", "比亚迪", "知乎", "得物", "Shopee", "Lazada",
    "Shein", "TikTok", "抖音", "字节跳动抖音", "飞书", "Lark",
], key=len, reverse=True)

_ROLES = sorted([
    "前端工程师", "前端开发", "前端", "后端工程师", "后端开发", "后端",
    "全栈工程师", "全栈", "Java工程师", "Java开发", "Java",
    "Python工程师", "Python开发", "Python", "Go工程师", "Go开发",
    "Go", "Golang", "React工程师", "Node.js工程师", "Node.js",
    "Node", "算法工程师", "算法", "数据工程师", "数据开发",
    "数据分析师", "数据分析", "数据科学家", "测试工程师", "测试开发",
    "测试", "QA", "DevOps工程师", "DevOps", "SRE工程师", "SRE",
    "产品经理", "产品", "产品负责人", "UI设计师", "UX设计师",
    "UI设计", "UX设计", "视觉设计", "交互设计", "架构师",
    "系统架构师", "技术架构师", "嵌入式工程师", "嵌入式开发", "嵌入式",
    "AI工程师", "AI", "机器学习工程师", "ML工程师",
    "NLP工程师", "NLP", "计算机视觉工程师", "CV工程师", "CV",
    "大数据工程师", "大数据开发", "推荐系统工程师",
    "安全工程师", "安全", "网络安全",
    "客户端工程师", "客户端开发", "iOS工程师", "iOS开发", "iOS",
    "Android工程师", "Android开发", "Android",
    "Flutter工程师", "Flutter开发", "Flutter",
    "音视频工程师", "音视频开发", "音视频",
    "HR", "HRBP", "招聘专员", "招聘经理",
], key=len, reverse=True)

_SKILLS = sorted([
    "Python", "Java", "Go", "Golang", "Rust", "C++", "C", "C#",
    "JavaScript", "TypeScript", "React", "Vue", "Angular", "Node.js",
    "Spring Boot", "Django", "Flask", "FastAPI", "Kubernetes", "K8s",
    "Docker", "AWS", "GCP", "Azure", "TensorFlow", "PyTorch",
    "Kafka", "Redis", "PostgreSQL", "MySQL", "MongoDB", "Elasticsearch",
    "Spark", "Flink", "Hadoop", "Figma", "Sketch",
], key=len, reverse=True)

# ── Regex Patterns ──

_RE_SALARY = re.compile(r"(?:薪资|薪酬|薪水|月薪|年薪|期望)?[约]?\s*(\d+)\s*[kK]")
_RE_SALARY_RANGE = re.compile(r"(?:薪资|薪酬|薪水|月薪|年薪)?[约]?\s*(\d+)\s*k?\s*[-~至到]\s*(\d+)\s*[kK]")
_RE_EXPERIENCE = re.compile(r"(\d+)\s*[年歲岁]")
_RE_EXPERIENCE_RANGE = re.compile(r"(\d+)\s*[-~至到]\s*(\d+)\s*[年歲岁]")
_RE_LOCATION = re.compile(r"(北京|上海|广州|深圳|杭州|成都|武汉|南京|西安|苏州|长沙|重庆|天津|厦门|珠海)")
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_RE_PHONE = re.compile(r"1[3-9]\d{9}")


# ── Extraction Functions ──


def extract_companies(text: str) -> list[str]:
    """Extract known company names from text, longest-first."""
    found: list[str] = []
    remaining = text
    for company in _COMPANIES:
        if company.lower() in remaining.lower():
            found.append(company)
            # Remove first occurrence to avoid overlaps
            idx = remaining.lower().find(company.lower())
            remaining = remaining[:idx] + remaining[idx + len(company):]
    return found


def extract_roles(text: str) -> list[str]:
    """Extract known role/position names from text."""
    found: list[str] = []
    remaining = text
    for role in _ROLES:
        if role.lower() in remaining.lower():
            found.append(role)
            idx = remaining.lower().find(role.lower())
            remaining = remaining[:idx] + remaining[idx + len(role):]
    return found


def extract_skills(text: str) -> list[str]:
    """Extract known skill keywords from text."""
    found: list[str] = []
    remaining = text
    for skill in _SKILLS:
        if skill.lower() in remaining.lower():
            found.append(skill)
            idx = remaining.lower().find(skill.lower())
            remaining = remaining[:idx] + remaining[idx + len(skill):]
    return found


def extract_salary(text: str) -> dict | None:
    """Extract salary info. Returns dict with min/max or None."""
    m = _RE_SALARY_RANGE.search(text)
    if m:
        return {"min_k": int(m.group(1)), "max_k": int(m.group(2))}
    m = _RE_SALARY.search(text)
    if m:
        val = int(m.group(1))
        return {"min_k": val, "max_k": val * 12 // 10}  # estimate ~20% range
    return None


def extract_experience(text: str) -> dict | None:
    """Extract experience years. Returns dict with min/max or None."""
    m = _RE_EXPERIENCE_RANGE.search(text)
    if m:
        return {"min_years": int(m.group(1)), "max_years": int(m.group(2))}
    m = _RE_EXPERIENCE.search(text)
    if m:
        val = int(m.group(1))
        return {"min_years": val, "max_years": val}
    return None


def extract_location(text: str) -> str | None:
    """Extract city from text."""
    m = _RE_LOCATION.search(text)
    return m.group(1) if m else None


def extract_candidate_name(text: str) -> str | None:
    """Extract candidate name after keywords like '给XX发offer' / '候选人XX'."""
    for prefix in ["候选人", "给"]:
        m = re.search(rf"{prefix}\s*([\u4e00-\u9fff]{{2,3}})(?:发|安排|写|做|看|送|通知|面试|办|来)", text)
        if m:
            candidate = m.group(1)
            if candidate not in ("公司", "我们", "他们", "大家", "这个"):
                return candidate
    return None


def extract_job_title(text: str, roles: list[str] | None = None) -> str | None:
    """Extract a generic job position title from context.

    Falls back to concatenating extracted roles if no explicit prefix match.
    """
    for prefix in ["招聘", "找", "JD", "jd", "职位", "岗位"]:
        m = re.search(rf"{prefix}[：:：\s]?(.+?)(?:[，,。\.]|$)", text)
        if m:
            title = m.group(1).strip()
            if len(title) < 30:
                return title
    if roles:
        title = "".join(roles)
        if title:
            return title
    return None


def extract_requirements(text: str) -> str | None:
    """Extract requirements text when it's explicitly after a keyword."""
    for prefix in ["要求", "需要", "任职资格", "岗位要求"]:
        m = re.search(rf"{prefix}[：: ](.+)", text)
        if m:
            return m.group(1).strip()
    # Fallback: if we detect JD intent, use raw text as requirement
    return None


# ── Action Inference ──


def infer_action(text: str, intent: str | None = None) -> str:
    """Infer action from text based on keyword rules, falling back to intent default."""
    text_lower = text.lower()
    for keywords, intent_filter, action in _ACTION_RULES:
        if intent_filter and intent_filter != intent:
            continue
        for kw in keywords:
            if kw.lower() in text_lower:
                logger.debug("infer_action: kw='%s' → action='%s' (intent=%s)", kw, action, intent)
                return action
    # Fallback to intent default
    if intent and intent in _INTENT_DEFAULT_ACTION:
        return _INTENT_DEFAULT_ACTION[intent]
    return "chat"


# ── Main Entry Point ──


def extract_params(text: str, intent: str | None = None) -> dict[str, Any]:
    """From raw NL text and optional intent, return enriched parameter dict.

    Returns a flat dict suitable for merging into RouterAgent's input_data
    before dispatching to Specialist Agent.
    """
    if not text:
        return {}

    params: dict[str, Any] = {}

    # 1. Action
    action = infer_action(text, intent)
    params["action"] = action

    # 2. Entities common across agents
    companies = extract_companies(text)
    if companies:
        params["target_companies"] = companies

    roles = extract_roles(text)
    if roles:
        params["target_roles"] = roles

    skills = extract_skills(text)
    if skills:
        params["skills"] = skills

    location = extract_location(text)
    if location:
        params["location"] = location

    # 3. Numeric params
    exp = extract_experience(text)
    if exp:
        params["experience_min"] = exp["min_years"]
        if exp["max_years"] != exp["min_years"]:
            params["experience_max"] = exp["max_years"]

    salary = extract_salary(text)
    if salary:
        params["salary_min"] = salary["min_k"]
        params["salary_max"] = salary["max_k"]

    # 4. Agent-specific extractions
    # Sourcing
    if intent == "jd_generation":
        title = extract_job_title(text, roles)
        if title:
            params["title"] = title
        req = extract_requirements(text)
        if req:
            params["requirements"] = req
        # If no explicit requirements, use full text
        if "requirements" not in params:
            params["requirements"] = text

    if intent == "outreach":
        name = extract_candidate_name(text)
        if name:
            params["candidate_name"] = name
        if companies:
            params["company"] = companies[0]
        if roles:
            params["role"] = roles[0]

    if intent == "offering":
        name = extract_candidate_name(text)
        if name:
            params["candidate_name"] = name
        if roles:
            params["role"] = roles[0]
        title = extract_job_title(text, roles)
        if title:
            params["title"] = title

    if intent == "onboarding":
        name = extract_candidate_name(text)
        if name:
            params["candidate_name"] = name
        title = extract_job_title(text, roles)
        if title:
            params["title"] = title

    if intent == "interview":
        name = extract_candidate_name(text)
        if name:
            params["candidate_name"] = name
        title = extract_job_title(text, roles)
        if title:
            params["job_title"] = title
        # Round detection
        round_map = {"R1": ["初筛", "电话面"], "R2": ["技术面", "技术"], "R3": ["行为", "系统设计", "架构"], "R4": ["终面", "交叉面", "HR面"]}
        for round_id, kws in round_map.items():
            for kw in kws:
                if kw in text:
                    params["round_id"] = round_id
                    break

    if intent == "channel_strategy":
        # Try to find budget from text
        budget_m = re.search(r"预算[约]?(\d+)", text)
        if budget_m:
            params["budget"] = float(budget_m.group(1))
        else:
            params["budget"] = 10000.0

    if intent in ("analytics", "report"):
        # For analytics, just set the action we already inferred
        pass

    logger.debug(
        "extract_params(intent=%s, text=%.40s) → %s",
        intent, text, params,
    )
    return params
