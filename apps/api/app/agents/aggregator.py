"""图4: Aggregator 模式 — 多角度并行评估后合并结果。"""

from __future__ import annotations

import json
import asyncio
from typing import Any

from app.agents.base import BaseAgent
from app.agents.single_agent import SingleAgent
from app.llm import get_llm_client

DIMENSION_PROMPTS: dict[str, str] = {
    "technical": """你是一位技术面试官，评估候选人的技术能力。
候选人信息: {candidate_info}
请从以下方面评估:
1. 技术栈匹配度 (0-10)
2. 项目经验深度 (0-10)
3. 技术问题解决能力 (0-10)
4. 学习能力与成长潜力 (0-10)

输出 JSON（不要输出其他内容）:
{{
  "dimension": "technical",
  "scores": {{ "match": 0-10, "depth": 0-10, "problem_solving": 0-10, "growth": 0-10 }},
  "overall": 0-10,
  "summary": "评估总结",
  "highlights": ["亮点1"],
  "concerns": ["顾虑1"]
}}""",
    "behavioral": """你是一位行为面试官，评估候选人的软性素质和团队适配度。
候选人信息: {candidate_info}
请从以下方面评估:
1. 沟通能力 (0-10)
2. 团队协作 (0-10)
3. 领导力 (0-10)
4. 文化适配度 (0-10)

输出 JSON（不要输出其他内容）:
{{
  "dimension": "behavioral",
  "scores": {{ "communication": 0-10, "teamwork": 0-10, "leadership": 0-10, "culture_fit": 0-10 }},
  "overall": 0-10,
  "summary": "评估总结",
  "highlights": ["亮点1"],
  "concerns": ["顾虑1"]
}}""",
    "experience": """你是一位资深行业专家，评估候选人的行业经验和职业发展轨迹。
候选人信息: {candidate_info}
请从以下方面评估:
1. 行业经验相关度 (0-10)
2. 职业发展轨迹 (0-10)
3. 成就影响力 (0-10)
4. 岗位匹配度 (0-10)

输出 JSON（不要输出其他内容）:
{{
  "dimension": "experience",
  "scores": {{ "relevance": 0-10, "career_track": 0-10, "impact": 0-10, "fit": 0-10 }},
  "overall": 0-10,
  "summary": "评估总结",
  "highlights": ["亮点1"],
  "concerns": ["顾虑1"]
}}""",
}

CONSENSUS_PROMPT = """你是一位招聘委员会主席，负责汇总多个维度的评估结果并给出最终结论。

多维度评估结果:
{evaluation_results}

请综合各维度评分，输出最终的录用建议 JSON（不要输出其他内容）:
{{
  "final_score": 0-10,
  "dimension_scores": {{
    "technical": 0-10,
    "behavioral": 0-10,
    "experience": 0-10
  }},
  "consensus_summary": "综合评估总结",
  "top_strengths": ["核心优势1", "核心优势2", "核心优势3"],
  "top_concerns": ["主要顾虑1", "主要顾虑2"],
  "recommendation": "strong_hire/hire/consider/pass",
  "next_steps": ["下一步1", "下一步2"]
}}"""


class AggregatorAgent(BaseAgent):
    """图4: Aggregator 模式 — 多角度并行评估后合并。

    适用于:
    - 多维度候选人评估
    - 多数据源报表聚合
    - 并行 LLM 调用结果合并
    """

    def __init__(self, name: str = "aggregator"):
        super().__init__(name)
        self.workers: list[SingleAgent] = []
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def add_worker(self, worker: SingleAgent) -> None:
        self.workers.append(worker)

    async def run_parallel(self, candidate_info: str, dimensions: list[str] | None = None) -> list[dict]:
        """并行执行多维度评估。"""
        active_dims = dimensions or list(DIMENSION_PROMPTS.keys())

        async def evaluate(dim: str) -> dict:
            prompt = DIMENSION_PROMPTS.get(dim, DIMENSION_PROMPTS["technical"])
            messages = [
                {"role": "system", "content": prompt.format(candidate_info=candidate_info)},
                {"role": "user", "content": f"请从 {dim} 维度评估该候选人。"},
            ]
            result = await self.llm.chat(messages, temperature=0.3, max_tokens=1024)
            try:
                parsed = json.loads(
                    result.strip().removeprefix("```json").removesuffix("```").strip()
                )
            except (json.JSONDecodeError, AttributeError):
                parsed = {"dimension": dim, "error": "parse_failed", "raw": result}
            return parsed

        tasks = [evaluate(dim) for dim in active_dims]
        return await asyncio.gather(*tasks)

    async def aggregate(self, results: list[dict]) -> dict:
        """合并多维度评估结果为最终结论。"""
        messages = [
            {"role": "system", "content": CONSENSUS_PROMPT.format(
                evaluation_results=json.dumps(results, ensure_ascii=False, indent=2),
            )},
            {"role": "user", "content": "请汇总各维度评估，给出最终结论。"},
        ]

        consensus_raw = await self.llm.chat(messages, temperature=0.3, max_tokens=1024)
        try:
            consensus = json.loads(
                consensus_raw.strip().removeprefix("```json").removesuffix("```").strip()
            )
        except (json.JSONDecodeError, AttributeError):
            consensus = {"error": "consensus_parse_failed", "raw": consensus_raw}

        return {
            "dimension_results": results,
            "consensus": consensus,
            "total_dimensions": len(results),
        }

    async def run(self, input_data: dict) -> dict:
        """运行完整 Aggregator 评估流程。"""
        candidate_info = input_data.get("candidate_info", "")
        dimensions = input_data.get("dimensions", None)

        dimension_results = await self.run_parallel(candidate_info, dimensions)
        aggregated = await self.aggregate(dimension_results)

        return {
            "agent": self.name,
            "status": "completed",
            **aggregated,
        }
