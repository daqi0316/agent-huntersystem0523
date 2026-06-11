"""P4: SourcingAnalyzeAgent — 技能提取/标准化 + 职业轨迹分析 + 候选人摘要生成 + JD匹配度评分"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.llm import get_llm_client
from app.llm.base import LLMClient

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """你是一个专业的招聘分析师助手。你的任务是从候选人的原始数据中提取结构化的分析结果。

请始终以 JSON 格式返回结果，不要包含其他文字。

## 技能提取规则
- 从原始数据中提取所有技能关键词（编程语言、框架、工具、领域知识）
- 标准化：Python=python, Node.js=nodejs, React=react, AWS=aws, Docker=docker 等
- 按类别分组：language/framework/tool/domain

## 职业轨迹分析
- 提取工作经历中的公司、职位、时间段
- 判断职业发展方向（如：从开发到架构、从大厂到创业）
- 评估稳定性（平均在职时长）
- 判断行业倾向

## 候选人摘要
- 一句话定位（如：5年经验Python后端工程师，专注高并发系统）
- 核心优势（3-5个要点）
- 潜在风险（如：跳槽频繁、技能单一、薪资预期过高）
- 推荐岗位类型（如：P7+ 后端架构师）
"""


def _extract_candidate_text(candidate: dict[str, Any]) -> str:
    """将候选人数据结构转为 LLM 可读的文本"""
    parts = []
    if candidate.get("name"):
        parts.append(f"姓名: {candidate['name']}")
    if candidate.get("current_title"):
        parts.append(f"当前职位: {candidate['current_title']}")
    if candidate.get("current_company"):
        parts.append(f"当前公司: {candidate['current_company']}")
    if candidate.get("location"):
        parts.append(f"地点: {candidate['location']}")
    if candidate.get("salary"):
        parts.append(f"薪资: {candidate['salary']}")
    if candidate.get("experience_years") is not None:
        parts.append(f"经验年限: {candidate['experience_years']}")
    if candidate.get("education"):
        parts.append(f"教育背景: {candidate['education']}")
    if candidate.get("skills"):
        parts.append(f"技能: {', '.join(candidate['skills'])}")
    if candidate.get("summary"):
        parts.append(f"简介: {candidate['summary']}")

    # 原始数据补充
    raw = candidate.get("raw_data") or {}
    for platform, data in raw.items():
        if isinstance(data, dict):
            extras = []
            for k, v in data.items():
                if k not in ("name", "title", "company", "salary") and v:
                    extras.append(f"{k}: {v}")
            if extras:
                parts.append(f"[{platform}] {'; '.join(extras)}")
    return "\n".join(parts)


def _normalize_skills(skills: list[str]) -> list[str]:
    """标准化技能名称"""
    skill_map = {
        "nodejs": "node.js", "node": "node.js",
        "reactjs": "react", "react.js": "react",
        "vuejs": "vue", "vue.js": "vue",
        "nextjs": "next.js", "next": "next.js",
        "ts": "typescript", "js": "javascript",
        "expressjs": "express", "express.js": "express",
        "k8s": "kubernetes",
        "tf": "tensorflow", "torch": "pytorch",
        "psql": "postgresql", "pg": "postgresql",
        "gp": "golang", "golang": "go",
    }
    seen = set()
    result = []
    for s in skills:
        s = s.strip().lower().replace(" ", "-")
        normalized = skill_map.get(s, s)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


async def analyze_candidate(candidate: dict[str, Any], llm: LLMClient | None = None) -> dict[str, Any]:
    """分析单个候选人：技能提取 + 职业轨迹 + 摘要

    Args:
        candidate: Candidate 模型字段 dict（含 raw_data）
        llm: LLMClient 实例，None 则自动获取

    Returns:
        {
            "skills_extracted": [...],       # 提取+标准化的技能
            "skill_categories": {...},        # 按类别分组的技能
            "career_trajectory": {...},       # 职业轨迹分析
            "summary": {...},                 # 候选人摘要
            "confidence": float,              # 整体置信度 0-1
        }
    """
    if llm is None:
        llm = get_llm_client()

    candidate_text = _extract_candidate_text(candidate)

    user_prompt = f"""请分析以下候选人数据，返回严格的 JSON（不要其他文字）：

```json
{{
  "skills_extracted": ["技能1", "技能2", ...],
  "skill_categories": {{
    "language": ["python", "javascript", ...],
    "framework": ["react", "django", ...],
    "tool": ["docker", "aws", ...],
    "domain": ["金融", "电商", ...]
  }},
  "career_trajectory": {{
    "direction": "职业发展方向描述",
    "stability": "稳定/一般/频繁",
    "avg_tenure_years": 2.5,
    "industry_trend": ["互联网", "金融"]
  }},
  "summary": {{
    "one_liner": "一句话定位",
    "strengths": ["优势1", "优势2", "优势3"],
    "risks": ["风险1", "风险2"],
    "recommended_roles": ["推荐岗位类型1"]
  }},
  "confidence": 0.85
}}
```

候选人数据：
{candidate_text}
"""
    try:
        reply = await llm.chat(
            [{"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
             {"role": "user", "content": user_prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
    except Exception as e:
        logger.warning("LLM analyze failed: %s", e)
        return _fallback_analysis(candidate)

    result = _parse_json(reply)
    if not result:
        logger.warning("Failed to parse LLM analysis result, using fallback")
        return _fallback_analysis(candidate)

    # 合并已有技能 + 标准化
    existing_skills = candidate.get("skills") or []
    extracted = result.get("skills_extracted") or []
    merged = list(dict.fromkeys(existing_skills + _normalize_skills(extracted)))
    result["skills_extracted"] = merged

    confidence = result.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
    result["confidence"] = min(max(float(confidence), 0.0), 1.0)

    return result


async def match_candidate_to_jd(
    candidate: dict[str, Any],
    analysis: dict[str, Any],
    jd_text: str,
    jd_requirements: str | None = None,
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    """JD 匹配度评分（LLM 多维度对比）

    Args:
        candidate: Candidate 字段 dict
        analysis: analyze_candidate() 返回的分析结果
        jd_text: JD 描述
        jd_requirements: JD 要求（可选）

    Returns:
        {
            "overall_score": 0.75,
            "dimensions": {
                "skills_match": {"score": 0.8, "matched": [...], "missing": [...]},
                "experience_match": {"score": 0.7, "detail": "..."},
                "industry_match": {"score": 0.6, "detail": "..."},
            },
            "summary": "综合评估",
            "confidence": 0.85,
        }
    """
    if llm is None:
        llm = get_llm_client()

    candidate_text = _extract_candidate_text(candidate)
    jd_section = f"JD描述:\n{jd_text}"
    if jd_requirements:
        jd_section += f"\n\n任职要求:\n{jd_requirements}"

    user_prompt = f"""请对比以下候选人与 JD 的匹配度，返回严格的 JSON：

```json
{{
  "overall_score": 0.0-1.0,
  "dimensions": {{
    "skills_match": {{
      "score": 0.0-1.0,
      "matched": ["匹配的技能"],
      "missing": ["缺失的关键技能"],
      "detail": "评估说明"
    }},
    "experience_match": {{
      "score": 0.0-1.0,
      "detail": "经验匹配评估"
    }},
    "industry_match": {{
      "score": 0.0-1.0,
      "detail": "行业背景匹配评估"
    }}
  }},
  "summary": "综合评估一句话",
  "confidence": 0.85
}}
```

候选人:
{candidate_text}

{jd_section}
"""
    try:
        reply = await llm.chat(
            [{"role": "system", "content": "你是一个专业的招聘匹配分析师。请严格按 JSON 格式返回匹配度评分。"},
             {"role": "user", "content": user_prompt}],
            temperature=0.2,
            max_tokens=2048,
        )
    except Exception as e:
        logger.warning("LLM match failed: %s", e)
        return {"overall_score": 0.5, "dimensions": {}, "summary": "LLM 不可用，使用默认评分", "confidence": 0.0}

    result = _parse_json(reply)
    if not result:
        return {"overall_score": 0.5, "dimensions": {}, "summary": "解析失败，使用默认评分", "confidence": 0.0}

    overall = result.get("overall_score", 0.5)
    result["overall_score"] = min(max(float(overall), 0.0), 1.0)
    conf = result.get("confidence", 0.5)
    result["confidence"] = min(max(float(conf), 0.0), 1.0)
    return result


def _fallback_analysis(candidate: dict[str, Any]) -> dict[str, Any]:
    """LLM 不可用时的规则兜底分析"""
    skills = candidate.get("skills") or []
    name = candidate.get("name", "")
    title = candidate.get("current_title", "")
    company = candidate.get("current_company", "")
    exp = candidate.get("experience_years")

    one_liner_parts = []
    if exp:
        one_liner_parts.append(f"{exp}年经验")
    if title:
        one_liner_parts.append(title)
    if company:
        one_liner_parts.append(f"曾在{company}")

    return {
        "skills_extracted": skills,
        "skill_categories": {"language": [], "framework": [], "tool": [], "domain": []},
        "career_trajectory": {
            "direction": "",
            "stability": "未知",
            "avg_tenure_years": None,
            "industry_trend": [],
        },
        "summary": {
            "one_liner": " ".join(one_liner_parts) or f"{name} 的基本信息",
            "strengths": [],
            "risks": [],
            "recommended_roles": [title] if title else [],
        },
        "confidence": 0.3,
    }


def _parse_json(reply: str) -> dict[str, Any] | None:
    """从 LLM 回复中提取 JSON（处理代码块包裹）"""
    if "```" in reply:
        for part in reply.split("```"):
            part = part.strip().removeprefix("json").strip()
            if part.startswith("{"):
                reply = part
                break
    start = reply.find("{")
    end = reply.rfind("}")
    if start != -1 and end != -1 and end > start:
        reply = reply[start: end + 1]
    try:
        return json.loads(reply)
    except json.JSONDecodeError as e:
        logger.warning("JSON parse error: %s", e)
        return None
