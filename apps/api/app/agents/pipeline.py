"""图2: 流水线模式 — AI初筛简历，多步骤 + Gate 质检。"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Coroutine

from app.agents.base import BaseAgent
from app.llm import get_llm_client
from app.llm.retry import llm_chat_with_retry

RESUME_PARSE_PROMPT = """你是一位资深的简历解析专家。
请从以下简历文本中提取结构化信息，以 JSON 格式返回（不要输出其他内容）。

返回格式:
{
  "name": "候选人姓名",
  "email": "邮箱",
  "phone": "电话",
  "skills": ["技能1", "技能2", ...],
  "experience_years": 总工作年数(数字),
  "education": {
    "degree": "最高学历",
    "major": "专业",
    "school": "毕业院校"
  },
  "recent_roles": ["最近职位1", "最近职位2"],
  "key_achievements": ["成就1", "成就2", ...]
}"""

RESUME_MATCH_PROMPT = """你是一位招聘匹配专家，负责将候选人简历与职位要求进行匹配分析。

职位要求:
{job_requirements}

候选人画像:
{parsed_resume}

请分析以下维度，输出 JSON（不要输出其他内容）:
{{
  "skills_match": {{ "score": 0-10, "matched": ["匹配的技能"], "missing": ["缺少的技能"], "extra": ["额外技能"] }},
  "experience_match": {{ "score": 0-10, "analysis": "经验匹配分析" }},
  "education_match": {{ "score": 0-10, "analysis": "学历匹配分析" }},
  "overall_score": 0-10,
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["劣势1", "劣势2"],
  "recommendation": "强烈推荐/推荐/待定/不推荐"
}}"""

SCREENING_GATE_PROMPT = """你是一位严格的招聘质检专家，审核以下初筛结果。

初筛结果:
{screening_result}

请判断:
1. 评分是否合理 — 与简历和职位要求匹配吗？
2. 是否有明显的误判？
3. 是否需要人工复审？

输出 JSON（不要输出其他内容）:
{{
  "gate_passed": true/false,
  "score_adjusted": 调整后的分数(0-10),
  "issues": ["问题1", "问题2"],
  "needs_human_review": true/false,
  "gate_summary": "质检总结一句话"
}}"""


class PipelineStep:
    """流水线中的单个步骤"""

    def __init__(
        self,
        name: str,
        handler: Callable[[dict], Coroutine[Any, Any, dict]],
    ):
        self.name = name
        self.handler = handler


class PipelineAgent(BaseAgent):
    """图2: 流水线模式 — 多步骤处理 + Gate 质检

    步骤示例:
    1. parse: 解析简历
    2. match: 匹配职位要求
    3. score: 综合评分
    4. gate: 质检通过/拒绝
    """

    def __init__(self, name: str = "pipeline"):
        super().__init__(name)
        self.steps: list[PipelineStep] = []
        self.context: dict[str, Any] = {}
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def add_step(self, name: str, handler: Callable[[dict], Coroutine[Any, Any, dict]]) -> PipelineAgent:
        self.steps.append(PipelineStep(name=name, handler=handler))
        return self

    async def run(self, input_data: dict) -> dict:
        """执行完整流水线，返回每一步的结果。"""
        pipeline_id = str(uuid.uuid4())[:8]
        step_results: list[dict] = []
        self.context = {"pipeline_id": pipeline_id, **input_data}

        for step in self.steps:
            step_context = await step.handler(self.context)
            self.context.update(step_context)

            step_result = {
                "step": step.name,
                "status": "completed",
                "output": step_context,
            }
            step_results.append(step_result)

        return {
            "agent": self.name,
            "pipeline_id": pipeline_id,
            "status": "completed",
            "steps": step_results,
            "final_output": self.context,
        }

    @staticmethod
    async def parse_resume(context: dict) -> dict:
        """Step 1: 用 LLM 解析简历文本。"""
        llm = get_llm_client()
        resume_text = context.get("resume_text", "")

        messages = [
            {"role": "system", "content": RESUME_PARSE_PROMPT},
            {"role": "user", "content": f"简历文本:\n{resume_text}"},
        ]

        result = await llm_chat_with_retry(llm, messages, temperature=0.1, max_tokens=1024)
        import json
        try:
            parsed = json.loads(result.strip().removeprefix("```json").removesuffix("```").strip())
        except (json.JSONDecodeError, AttributeError):
            parsed = {"raw": result, "error": "parse_failed"}

        return {"parsed_resume": parsed}

    @staticmethod
    async def match_job(context: dict) -> dict:
        """Step 2: 将简历与职位要求匹配。"""
        llm = get_llm_client()
        parsed = context.get("parsed_resume", {})
        job_requirements = context.get("job_requirements", "无")

        messages = [
            {"role": "system", "content": RESUME_MATCH_PROMPT.format(
                job_requirements=job_requirements,
                parsed_resume=str(parsed),
            )},
            {"role": "user", "content": "请进行匹配分析。"},
        ]

        result = await llm_chat_with_retry(llm, messages, temperature=0.3, max_tokens=1024)
        import json
        try:
            match_result = json.loads(result.strip().removeprefix("```json").removesuffix("```").strip())
        except (json.JSONDecodeError, AttributeError):
            match_result = {"error": "parse_failed", "raw": result}

        return {"match_result": match_result}

    @staticmethod
    async def gate_check(context: dict) -> dict:
        """Step 3: Gate 质检。"""
        llm = get_llm_client()
        match_result = context.get("match_result", {})
        overall_score = match_result.get("overall_score", 0)

        messages = [
            {"role": "system", "content": SCREENING_GATE_PROMPT.format(
                screening_result=str(match_result),
            )},
            {"role": "user", "content": "请进行质检审核。"},
        ]

        result = await llm_chat_with_retry(llm, messages, temperature=0.2, max_tokens=512)
        import json
        try:
            gate = json.loads(result.strip().removeprefix("```json").removesuffix("```").strip())
        except (json.JSONDecodeError, AttributeError):
            gate = {"gate_passed": overall_score >= 6, "issues": ["gate_parse_failed"]}

        final_score = gate.get("score_adjusted", overall_score)
        gate_passed = gate.get("gate_passed", final_score >= 6)

        return {
            "gate_result": gate,
            "final_score": final_score,
            "gate_passed": gate_passed,
            "needs_human_review": gate.get("needs_human_review", False),
        }

    @staticmethod
    def build_screening_pipeline() -> PipelineAgent:
        """工厂方法：创建标准的简历初筛流水线。"""
        pipeline = PipelineAgent(name="resume_screening")
        pipeline.add_step("parse", PipelineAgent.parse_resume)
        pipeline.add_step("match", PipelineAgent.match_job)
        pipeline.add_step("gate", PipelineAgent.gate_check)
        return pipeline
