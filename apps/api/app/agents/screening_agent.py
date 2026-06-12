"""统一 ScreeningAgent — Pipeline + Aggregator 封装。

提供 6 维度评估、风险标记、批量对比输出。
LLM 优先（使用 prompts/screening.md），Pipeline 次之，规则兜底。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.pipeline import PipelineAgent
from app.agentops.instrumentation.recruitment import RecruitmentEvents
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

SCREENING_DIMENSIONS = [
    "technical",
    "experience",
    "education",
    "skills",
    "culture",
    "potential",
]

RISK_TAGS = {
    "gap": "简历中超过 3 个月的空窗期未说明",
    "job_hopping": "每份工作不足 1 年",
    "skill_inflation": "技能描述可能存在夸大",
    "salary_mismatch": "期望薪资与市场水平偏差 > 50%",
}

_KEYWORD_MAP = {
    "python": "technical",
    "java": "technical",
    "react": "technical",
    "aws": "technical",
    "docker": "technical",
    "sql": "technical",
    "管理": "experience",
    "lead": "experience",
    "负责": "experience",
    "硕士": "education",
    "博士": "education",
    "本科": "education",
    "团队": "culture",
    "沟通": "culture",
    "协作": "culture",
    "成长": "potential",
    "学习": "potential",
}


def _estimate_years(text: str) -> float:
    """从简历文本中粗略估算工作年限（规则兜底用）。"""
    patterns = [
        r"(\d+)\s*年.*经验",
        r"(\d+)\s*年.*工作",
        r"工作.*?(\d+)\s*年",
        r"经验.*?(\d+)\s*年",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return float(m.group(1))
    date_ranges = re.findall(r"(\d{4})[年/-](\d{0,2})[月/-]?\s*[-–~至到]\s*(\d{4})[年/-](\d{0,2})[月/-]?", text)
    if date_ranges:
        total = 0.0
        for y1, _, y2, _ in date_ranges:
            try:
                total += max(0, int(y2) - int(y1))
            except ValueError:
                pass
        return total if total > 0 else 3.0
    return 3.0


class ScreeningAgent(BaseAgent):
    """简历筛选 Agent — 初筛 + 多维评估 + 批量筛选 (LLM + pipeline + 规则兜底)。"""

    output_keys = ["results", "passed_ids"]

    def __init__(self, name: str = "screening"):
        super().__init__(name)
        self._llm = None
        self._pipeline: PipelineAgent | None = None
        self._aggregator = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    @property
    def pipeline(self) -> PipelineAgent:
        if self._pipeline is None:
            self._pipeline = PipelineAgent.build_screening_pipeline()
        return self._pipeline

    @property
    def aggregator(self):
        if self._aggregator is None:
            from app.agents.aggregator import AggregatorAgent
            self._aggregator = AggregatorAgent(name="screening_aggregator")
        return self._aggregator

    # ── LLM 辅助 ──

    async def _llm_json_chat(self, user_prompt: str, temperature: float = 0.2, max_tokens: int = 2048) -> dict | None:
        """调用 LLM（system_prompt from prompts/screening.md）并解析 JSON。"""
        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            reply = await self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
            if "```" in reply:
                parts = reply.split("```")
                for p in parts:
                    p = p.strip()
                    if p.startswith("{") or p.startswith("["):
                        reply = p
                        break
            start = reply.find("{")
            end = reply.rfind("}")
            if start != -1 and end != -1 and end > start:
                reply = reply[start: end + 1]
            return json.loads(reply)
        except Exception as e:
            logger.warning("ScreeningAgent LLM call failed: %s", e)
            return None

    # ── LLM 优先筛选 ──

    async def _llm_screen(self, resume_text: str, job_requirements: str) -> dict | None:
        """使用 self.system_prompt 进行 LLM 初筛。"""
        if not self.system_prompt:
            return None
        user_prompt = (
            f"请解析以下简历并进行岗位匹配分析。\n\n"
            f"职位要求：\n{job_requirements}\n\n"
            f"简历文本：\n{resume_text}\n\n"
            f"输出 JSON 格式：{{\n"
            f'  "parsed_resume": {{"name": "", "skills": [], "experience_years": 0}},\n'
            f'  "match": {{"overall_score": 0, "recommendation": "强烈推荐|推荐|待定|不推荐",\n'
            f'    "strengths": [], "weaknesses": [], "dimension_scores": {{}} }},\n'
            f'  "gate": {{"gate_passed": true, "needs_human_review": false, "gate_summary": ""}}\n'
            f"}}"
        )
        return await self._llm_json_chat(user_prompt, temperature=0.2, max_tokens=2048)

    # ── Pipeline 筛选 ──

    async def _pipeline_screen(self, resume_text: str, job_requirements: str) -> dict:
        """Pipeline Agent 筛选（硬编码 Prompt 兜底）。"""
        result = await self.pipeline.run({
            "resume_text": resume_text,
            "job_requirements": job_requirements,
        })
        return {
            "parsed_resume": result.get("final_output", {}).get("parsed_resume", {}),
            "match": result.get("final_output", {}).get("match_result", {}),
            "gate": result.get("final_output", {}).get("gate_result", {}),
            "final_score": result.get("final_output", {}).get("final_score", 0),
            "gate_passed": result.get("final_output", {}).get("gate_passed", False),
        }

    # ── 规则兜底 ──

    def _rule_screen(self, resume_text: str, job_requirements: str) -> dict:
        """关键词规则兜底筛选。"""
        matched_dims: dict[str, list[str]] = {}
        text_lower = resume_text.lower()
        requirements_lower = job_requirements.lower()
        for kw, dim in _KEYWORD_MAP.items():
            if kw.lower() in text_lower:
                matched_dims.setdefault(dim, []).append(kw)

        required_kws = [kw for kw in _KEYWORD_MAP if kw.lower() in requirements_lower]
        match_pct = len(required_kws) / max(len(_KEYWORD_MAP), 1) * 100 if required_kws else 30.0

        return {
            "parsed_resume": {
                "raw_text_snippet": resume_text[:500],
                "matched_keywords": {d: kws for d, kws in matched_dims.items()},
                "experience_years": _estimate_years(resume_text),
            },
            "match": {
                "overall_score": min(match_pct, 100),
                "dimension_scores": {dim: 5 for dim in SCREENING_DIMENSIONS},
                "recommendation": "待定" if match_pct < 40 else "建议面试",
                "strengths": list(matched_dims.keys()),
                "weaknesses": [],
            },
            "gate": {"gate_passed": match_pct >= 30, "needs_human_review": True, "gate_summary": "规则兜底筛选 - 需人工复核"},
            "final_score": min(match_pct, 100),
            "gate_passed": match_pct >= 30,
        }

    # ── 统一 screen ──

    async def screen(
        self,
        candidate_id: str,
        job_id: str,
        resume_text: str,
        job_requirements: str,
    ) -> dict[str, Any]:
        """单候选人初筛全流程：LLM(system_prompt) → Pipeline → 规则兜底。"""
        screen_result = None

        # 1. LLM 优先（使用 prompts/screening.md）
        llm_out = await self._llm_screen(resume_text, job_requirements)
        if llm_out and "gate" in llm_out:
            parsed = llm_out.get("parsed_resume", {})
            match = llm_out.get("match", {})
            gate = llm_out.get("gate", {})
            final_score = match.get("overall_score", 0)
            gate_passed = gate.get("gate_passed", final_score >= 6)
            screen_result = {
                "parsed_resume": parsed,
                "dimensions": match,
                "gate": gate,
                "final_score": final_score,
                "gate_passed": gate_passed,
                "needs_human_review": gate.get("needs_human_review", False),
                "source": "llm",
            }

        # 2. Pipeline 兜底（硬编码 Prompt）
        if screen_result is None:
            try:
                pipe = await self._pipeline_screen(resume_text, job_requirements)
                parsed = pipe.get("parsed_resume", {})
                match = pipe.get("match", {})
                gate = pipe.get("gate", {})
                final_score = pipe.get("final_score", match.get("overall_score", 0))
                gate_passed = pipe.get("gate_passed", False)
                screen_result = {
                    "parsed_resume": parsed,
                    "dimensions": match,
                    "gate": gate,
                    "final_score": final_score,
                    "gate_passed": gate_passed,
                    "needs_human_review": gate.get("needs_human_review", False),
                    "source": "pipeline",
                }
            except Exception as e:
                logger.warning("Pipeline screening failed: %s", e)

        # 3. 规则兜底
        if screen_result is None:
            logger.warning("LLM & Pipeline both failed, falling back to rules for %s", candidate_id)
            rule = self._rule_screen(resume_text, job_requirements)
            screen_result = {
                "parsed_resume": rule["parsed_resume"],
                "dimensions": rule["match"],
                "gate": rule["gate"],
                "final_score": rule["final_score"],
                "gate_passed": rule["gate_passed"],
                "needs_human_review": True,
                "source": "rules",
            }

        risks = self._detect_risks(screen_result["parsed_resume"], screen_result["dimensions"])
        gate = screen_result.get("gate", {})

        # P2-C Stage 9: 发射筛选业务事件
        dims = screen_result["dimensions"]
        await RecruitmentEvents.on_screening_completed(
            candidate_id=candidate_id,
            job_id=job_id,
            match_score=screen_result["final_score"] / 100,  # 0-100 → 0-1
            decision="advance" if screen_result["gate_passed"] else "reject",
            dimension_scores=dims.get("dimension_scores") if isinstance(dims, dict) else None,
            reason_codes=[r.get("type", "") for r in risks] if risks else None,
            needs_human_review=screen_result["needs_human_review"],
        )

        return {
            "candidate_id": candidate_id,
            "job_id": job_id,
            "overall_score": screen_result["final_score"],
            "parsed_resume": screen_result["parsed_resume"],
            "dimensions": screen_result["dimensions"],
            "gate_passed": screen_result["gate_passed"],
            "needs_human_review": screen_result["needs_human_review"],
            "source": screen_result.get("source", "unknown"),
            "risks": risks,
            "strengths": screen_result["dimensions"].get("strengths", []),
            "weaknesses": screen_result["dimensions"].get("weaknesses", []),
            "recommendation": screen_result["dimensions"].get("recommendation", ""),
            "summary": gate.get("gate_summary", ""),
        }

    # ── 6 维度评估 ──

    async def multi_evaluate(
        self,
        candidate_info: str,
        dimensions: list[str] | None = None,
    ) -> dict[str, Any]:
        """6 维度并行评估候选人（LLM 优先）。"""
        dims = dimensions or SCREENING_DIMENSIONS
        if self.system_prompt:
            user_prompt = (
                f"请对以下候选人进行多维度评估（维度：{', '.join(dims)}）。\n\n"
                f"候选人信息：{candidate_info}\n\n"
                f"输出 JSON：{{\n"
                f'  "dimension_results": [{{\n'
                f'    "dimension": "维度名", "overall": 0-10, "summary": "评价", "scores": {{}}\n'
                f"  }}]\n"
                f"}}"
            )
            llm_out = await self._llm_json_chat(user_prompt)
            if llm_out and "dimension_results" in llm_out:
                return llm_out

        # Aggregator 兜底
        try:
            result = await self.aggregator.run({"candidate_info": candidate_info, "dimensions": dims[:3]})
            extra_dims = dims[3:]
            if extra_dims:
                for dim in extra_dims:
                    result.setdefault("dimension_results", []).append({
                        "dimension": dim, "overall": 5,
                        "summary": f"{dim} 维度评估（降级默认分）", "scores": {},
                    })
            return result
        except Exception as e:
            logger.warning("Aggregator evaluate failed: %s", e)
            return {"dimension_results": [{"dimension": d, "overall": 5, "summary": "默认中等分", "scores": {}} for d in dims]}

    async def batch_screen(
        self,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """批量候选人初筛，输出对比矩阵。"""
        results = []
        for c in candidates:
            try:
                r = await self.screen(
                    candidate_id=c.get("id", ""),
                    job_id=c.get("job_id", ""),
                    resume_text=c.get("resume_text", ""),
                    job_requirements=c.get("job_requirements", ""),
                )
                results.append(r)
            except Exception as e:
                logger.warning("Batch screen failed for candidate %s: %s", c.get("id"), e)
                results.append({"candidate_id": c.get("id"), "error": str(e)})

        headers = ["候选人", "总分", "推荐等级", "风险", "状态"]
        rows = []
        for r in results:
            if "error" in r:
                rows.append([r.get("candidate_id", "?"), "Error", "-", "-", "failed"])
            else:
                rows.append([
                    r.get("candidate_id", "?"),
                    str(r.get("overall_score", 0)),
                    r.get("recommendation", "未知"),
                    ", ".join(r.get("risks", [])),
                    "通过" if r.get("gate_passed") else "拒绝",
                ])

        return {
            "total": len(candidates),
            "passed": sum(1 for r in results if r.get("gate_passed")),
            "failed": sum(1 for r in results if r.get("error") or not r.get("gate_passed")),
            "results": results,
            "comparison_matrix": {"headers": headers, "rows": rows},
        }

    def _detect_risks(self, parsed: dict, match: dict) -> list[dict]:
        risks = []
        exp_years = parsed.get("experience_years", 0)
        if exp_years and exp_years < 2:
            risks.append({"type": "gap", "detail": RISK_TAGS["gap"], "level": "info"})
        if match.get("recommendation") == "待定":
            risks.append({"type": "job_hopping", "detail": RISK_TAGS["job_hopping"], "level": "warning"})
        skills = parsed.get("skills", [])
        matched_kws = parsed.get("matched_keywords", {})
        if len(skills) > 15 or sum(len(v) for v in matched_kws.values()) > 10:
            risks.append({"type": "skill_inflation", "detail": RISK_TAGS["skill_inflation"], "level": "warning"})
        return risks

    async def run(self, input_data: dict) -> dict:
        """Agent 入口。"""
        action = input_data.get("action", "screen")

        if action == "batch":
            result = await self.batch_screen(input_data.get("candidates", []))
            passed_ids = [r.get("candidate_id") for r in result.get("results", []) if r.get("gate_passed")]
            return self.format_result("completed", result, f"批量筛选完成: {result.get('total', 0)} 人, {result.get('passed', 0)} 通过")
        elif action == "evaluate":
            result = await self.multi_evaluate(
                input_data.get("candidate_info", ""),
                input_data.get("dimensions"),
            )
            return self.format_result("completed", result, "多维度评估完成")
        else:
            result = await self.screen(
                candidate_id=input_data.get("candidate_id", ""),
                job_id=input_data.get("job_id", ""),
                resume_text=input_data.get("resume_text", ""),
                job_requirements=input_data.get("job_requirements", ""),
            )
            return self.format_result(
                "completed",
                result,
                f"候选人 {result.get('candidate_id', '?')} 评分 {result.get('overall_score', 0):.0f}/100",
            )
