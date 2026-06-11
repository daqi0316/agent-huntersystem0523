"""Tests for analyze_agent.py — P4 AI 分析核心逻辑."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.sourcing.analyze_agent import (
    _extract_candidate_text,
    _fallback_analysis,
    _normalize_skills,
    _parse_json,
    analyze_candidate,
    match_candidate_to_jd,
)


# ── _normalize_skills ──


class TestNormalizeSkills:
    def test_basic_normalization(self):
        """常用技能别名归一化"""
        result = _normalize_skills(["nodejs", "reactjs", "ts", "k8s", "golang"])
        assert result == ["node.js", "react", "typescript", "kubernetes", "go"]

    def test_case_insensitive(self):
        """大小写不敏感"""
        result = _normalize_skills(["NodeJS", "ReactJS", "K8S"])
        assert result == ["node.js", "react", "kubernetes"]

    def test_whitespace_to_hyphen(self):
        """空格转连字符"""
        result = _normalize_skills(["machine learning", "deep learning"])
        assert result == ["machine-learning", "deep-learning"]

    def test_deduplication(self):
        """重复技能去重"""
        result = _normalize_skills(["python", "python", "PYTHON", "Python"])
        assert result == ["python"]

    def test_unknown_skill_preserved(self):
        """未在映射表中的技能保留原名"""
        result = _normalize_skills(["rust", "zig"])
        assert result == ["rust", "zig"]

    def test_empty_input(self):
        """空列表"""
        result = _normalize_skills([])
        assert result == []


# ── _extract_candidate_text ──


class TestExtractCandidateText:
    def test_full_candidate(self, sample_candidate):
        """完整候选人生成文本"""
        text = _extract_candidate_text(sample_candidate)
        assert "张三" in text
        assert "Python高级工程师" in text
        assert "字节跳动" in text
        assert "北京" in text
        assert "35K-50K" in text
        assert "5" in text or "经验年限" in text
        assert "python" in text
        assert "5年后端开发经验" in text
        # raw_data 补充
        assert "boss_zhipin" in text

    def test_minimal_candidate(self, sample_candidate_minimal):
        """最少字段候选人"""
        text = _extract_candidate_text(sample_candidate_minimal)
        assert "李四" in text
        assert "java" in text

    def test_empty_candidate(self):
        """空 dict"""
        text = _extract_candidate_text({})
        assert text == ""

    def test_experience_years_zero(self):
        """0 年经验"""
        text = _extract_candidate_text({"name": "赵六", "experience_years": 0})
        assert "经验年限: 0" in text


# ── _parse_json ──


class TestParseJson:
    def test_plain_json(self):
        """纯 JSON 字符串"""
        result = _parse_json('{"skills_extracted": ["python"]}')
        assert result == {"skills_extracted": ["python"]}

    def test_markdown_code_block_json(self):
        """```json...``` 包裹"""
        reply = """```json
{"skills_extracted": ["python"], "confidence": 0.85}
```"""
        result = _parse_json(reply)
        assert result == {"skills_extracted": ["python"], "confidence": 0.85}

    def test_markdown_code_block_no_lang(self):
        """```...``` 无语言标记"""
        reply = """```{"name": "test"}```"""
        result = _parse_json(reply)
        assert result == {"name": "test"}

    def test_extra_text_before_after(self):
        """JSON 前后有额外文字"""
        reply = "分析结果：\n{\"score\": 0.9}\n以上。"
        result = _parse_json(reply)
        assert result == {"score": 0.9}

    def test_malformed_json(self):
        """格式错误的 JSON -> None"""
        result = _parse_json("这不是 JSON")
        assert result is None

    def test_empty_string(self):
        """空字符串 -> None"""
        result = _parse_json("")
        assert result is None

    def test_nested_json(self):
        """嵌套 JSON"""
        reply = '{"summary": {"one_liner": "test"}, "skills": ["a", "b"]}'
        result = _parse_json(reply)
        assert result["summary"]["one_liner"] == "test"
        assert result["skills"] == ["a", "b"]


# ── _fallback_analysis ──


class TestFallbackAnalysis:
    def test_full_candidate(self, sample_candidate):
        """完整候选人生成合理兜底"""
        result = _fallback_analysis(sample_candidate)
        assert result["skills_extracted"] == ["python", "django", "docker"]
        assert result["confidence"] == 0.3
        assert "5年经验" in result["summary"]["one_liner"]
        assert "Python高级工程师" in result["summary"]["one_liner"]
        assert "字节跳动" in result["summary"]["one_liner"]

    def test_minimal_candidate(self, sample_candidate_minimal):
        """最少字段候选人"""
        result = _fallback_analysis(sample_candidate_minimal)
        assert result["skills_extracted"] == ["java"]
        assert "李四" in result["summary"]["one_liner"]

    def test_empty_candidate(self):
        """空 dict"""
        result = _fallback_analysis({})
        assert result["skills_extracted"] == []
        assert result["confidence"] == 0.3
        assert "的基本信息" in result["summary"]["one_liner"]

    def test_no_name(self):
        """无姓名"""
        result = _fallback_analysis({"skills": ["go"]})
        assert result["skills_extracted"] == ["go"]

    def test_structure(self):
        """返回结构完整性"""
        result = _fallback_analysis({})
        assert "skills_extracted" in result
        assert "skill_categories" in result
        assert "career_trajectory" in result
        assert "summary" in result
        assert "confidence" in result
        assert result["skill_categories"] == {"language": [], "framework": [], "tool": [], "domain": []}


# ── analyze_candidate ──


class TestAnalyzeCandidate:
    async def test_success(self, mock_llm_client, sample_candidate):
        """LLM 正常返回"""
        llm_reply = json.dumps({
            "skills_extracted": ["python", "django", "docker", "postgresql"],
            "skill_categories": {
                "language": ["python"],
                "framework": ["django"],
                "tool": ["docker", "postgresql"],
                "domain": ["互联网"],
            },
            "career_trajectory": {
                "direction": "后端开发方向",
                "stability": "稳定",
                "avg_tenure_years": 2.5,
                "industry_trend": ["互联网"],
            },
            "summary": {
                "one_liner": "5年经验Python后端工程师",
                "strengths": ["Python熟练", "Django经验"],
                "risks": ["技能单一"],
                "recommended_roles": ["高级后端工程师"],
            },
            "confidence": 0.85,
        })
        mock_llm_client.chat.return_value = llm_reply

        result = await analyze_candidate(sample_candidate, llm=mock_llm_client)

        # existing_skills + _normalize_skills(extracted), dict.fromkeys 去重
        assert result["skills_extracted"] == ["python", "django", "docker", "postgresql"]
        assert result["confidence"] == 0.85
        assert result["summary"]["one_liner"] == "5年经验Python后端工程师"

    async def test_llm_fallback_on_exception(self, mock_llm_client, sample_candidate):
        """LLM 抛异常时走 fallback"""
        mock_llm_client.chat.side_effect = Exception("LLM API error")

        result = await analyze_candidate(sample_candidate, llm=mock_llm_client)

        assert result["confidence"] == 0.3  # fallback 置信度
        assert result["skills_extracted"] == ["python", "django", "docker"]

    async def test_llm_fallback_on_parse_failure(self, mock_llm_client, sample_candidate):
        """LLM 返回非 JSON 时走 fallback"""
        mock_llm_client.chat.return_value = "抱歉，我无法分析这个候选人"

        result = await analyze_candidate(sample_candidate, llm=mock_llm_client)

        assert result["confidence"] == 0.3
        assert result["skills_extracted"] == ["python", "django", "docker"]

    async def test_confidence_clamping(self, mock_llm_client, sample_candidate):
        """置信度 0-1 范围限制"""
        llm_reply = json.dumps({
            "skills_extracted": ["python"],
            "skill_categories": {},
            "career_trajectory": {},
            "summary": {"one_liner": "", "strengths": [], "risks": [], "recommended_roles": []},
            "confidence": 1.5,
        })
        mock_llm_client.chat.return_value = llm_reply

        result = await analyze_candidate(sample_candidate, llm=mock_llm_client)
        assert result["confidence"] == 1.0

        mock_llm_client.chat.return_value = json.dumps({
            "skills_extracted": [],
            "skill_categories": {},
            "career_trajectory": {},
            "summary": {"one_liner": "", "strengths": [], "risks": [], "recommended_roles": []},
            "confidence": -0.5,
        })
        result = await analyze_candidate(sample_candidate, llm=mock_llm_client)
        assert result["confidence"] == 0.0

    async def test_confidence_non_numeric(self, mock_llm_client, sample_candidate):
        """非数值置信度降级"""
        llm_reply = json.dumps({
            "skills_extracted": [],
            "skill_categories": {},
            "career_trajectory": {},
            "summary": {"one_liner": "", "strengths": [], "risks": [], "recommended_roles": []},
            "confidence": "high",
        })
        mock_llm_client.chat.return_value = llm_reply

        result = await analyze_candidate(sample_candidate, llm=mock_llm_client)
        assert result["confidence"] == 0.5

    async def test_skill_merge_with_existing(self, mock_llm_client, sample_candidate):
        """已有技能与 LLM 提取技能合并去重"""
        llm_reply = json.dumps({
            "skills_extracted": ["python", "kubernetes"],
            "skill_categories": {},
            "career_trajectory": {},
            "summary": {"one_liner": "", "strengths": [], "risks": [], "recommended_roles": []},
            "confidence": 0.9,
        })
        mock_llm_client.chat.return_value = llm_reply

        result = await analyze_candidate(sample_candidate, llm=mock_llm_client)
        # python 在 skills 和 LLM 结果中都有 -> 只出现一次
        assert result["skills_extracted"].count("python") == 1
        assert "kubernetes" in result["skills_extracted"]

    async def test_minimal_candidate(self, mock_llm_client, sample_candidate_minimal):
        """最少字段候选人也可分析"""
        llm_reply = json.dumps({
            "skills_extracted": ["java"],
            "skill_categories": {"language": ["java"], "framework": [], "tool": [], "domain": []},
            "career_trajectory": {"direction": "", "stability": "未知", "avg_tenure_years": None, "industry_trend": []},
            "summary": {"one_liner": "Java开发者", "strengths": [], "risks": [], "recommended_roles": ["Java工程师"]},
            "confidence": 0.7,
        })
        mock_llm_client.chat.return_value = llm_reply

        result = await analyze_candidate(sample_candidate_minimal, llm=mock_llm_client)
        assert result["skills_extracted"] == ["java"]

    async def test_mock_called_with_correct_args(self, mock_llm_client, sample_candidate):
        """LLM.chat 被正确参数调用"""
        mock_llm_client.chat.return_value = json.dumps({
            "skills_extracted": [],
            "skill_categories": {},
            "career_trajectory": {},
            "summary": {"one_liner": "", "strengths": [], "risks": [], "recommended_roles": []},
            "confidence": 0.5,
        })

        await analyze_candidate(sample_candidate, llm=mock_llm_client)

        mock_llm_client.chat.assert_called_once()
        args, kwargs = mock_llm_client.chat.call_args
        messages = args[0]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] is not None
        assert "张三" in messages[1]["content"]
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 2048


# ── match_candidate_to_jd ──


class TestMatchCandidateToJd:
    async def test_success(self, mock_llm_client, sample_candidate, sample_jd_text):
        """JD 匹配正常返回"""
        analysis = {
            "skills_extracted": ["python", "django"],
            "skill_categories": {"language": ["python"], "framework": ["django"], "tool": [], "domain": []},
            "career_trajectory": {"direction": "后端", "stability": "稳定", "avg_tenure_years": 3, "industry_trend": ["互联网"]},
            "summary": {"one_liner": "Python后端", "strengths": [], "risks": [], "recommended_roles": []},
            "confidence": 0.8,
        }

        llm_reply = json.dumps({
            "overall_score": 0.85,
            "dimensions": {
                "skills_match": {"score": 0.8, "matched": ["python", "django"], "missing": ["消息队列"], "detail": "技能匹配度较高"},
                "experience_match": {"score": 0.9, "detail": "5年经验符合要求"},
                "industry_match": {"score": 0.7, "detail": "互联网背景匹配"},
            },
            "summary": "候选人基本符合要求",
            "confidence": 0.85,
        })
        mock_llm_client.chat.return_value = llm_reply

        result = await match_candidate_to_jd(sample_candidate, analysis, sample_jd_text, llm=mock_llm_client)

        assert result["overall_score"] == 0.85
        assert result["dimensions"]["skills_match"]["matched"] == ["python", "django"]
        assert result["dimensions"]["skills_match"]["missing"] == ["消息队列"]
        assert result["summary"] == "候选人基本符合要求"

    async def test_with_requirements(self, mock_llm_client, sample_candidate, sample_jd_text, sample_jd_requirements):
        """JD 带任职要求"""
        llm_reply = json.dumps({
            "overall_score": 0.8, "dimensions": {}, "summary": "符合", "confidence": 0.8,
        })
        mock_llm_client.chat.return_value = llm_reply

        result = await match_candidate_to_jd(
            sample_candidate, {}, sample_jd_text, jd_requirements=sample_jd_requirements, llm=mock_llm_client,
        )
        assert result["overall_score"] == 0.8

    async def test_llm_failure(self, mock_llm_client, sample_candidate, sample_jd_text):
        """LLM 不可用返回默认评分"""
        mock_llm_client.chat.side_effect = Exception("API error")

        result = await match_candidate_to_jd(sample_candidate, {}, sample_jd_text, llm=mock_llm_client)

        assert result["overall_score"] == 0.5
        assert result["confidence"] == 0.0

    async def test_parse_failure(self, mock_llm_client, sample_candidate, sample_jd_text):
        """解析失败返回默认评分"""
        mock_llm_client.chat.return_value = "不是 JSON"

        result = await match_candidate_to_jd(sample_candidate, {}, sample_jd_text, llm=mock_llm_client)

        assert result["overall_score"] == 0.5
        assert result["confidence"] == 0.0

    async def test_score_clamping(self, mock_llm_client, sample_candidate, sample_jd_text):
        """评分 0-1 范围限制"""
        llm_reply = json.dumps({
            "overall_score": 1.8, "dimensions": {}, "summary": "x", "confidence": 0.5,
        })
        mock_llm_client.chat.return_value = llm_reply

        result = await match_candidate_to_jd(sample_candidate, {}, sample_jd_text, llm=mock_llm_client)
        assert result["overall_score"] == 1.0

    async def test_mock_called_with_correct_args(self, mock_llm_client, sample_candidate, sample_jd_text):
        """LLM.chat 被正确参数调用"""
        mock_llm_client.chat.return_value = json.dumps({
            "overall_score": 0.5, "dimensions": {}, "summary": "", "confidence": 0.5,
        })

        await match_candidate_to_jd(sample_candidate, {}, sample_jd_text, llm=mock_llm_client)

        mock_llm_client.chat.assert_called_once()
        args, kwargs = mock_llm_client.chat.call_args
        messages = args[0]
        assert len(messages) == 2
        assert sample_jd_text in messages[1]["content"]
        assert kwargs["temperature"] == 0.2
