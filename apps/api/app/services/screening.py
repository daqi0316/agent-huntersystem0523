"""AI 初筛服务 — Pipeline 流水线 + Aggregator 多维度评估。"""

from __future__ import annotations

import logging

from app.agents.pipeline import PipelineAgent
from app.agents.aggregator import AggregatorAgent

logger = logging.getLogger(__name__)


class ScreeningService:
    """AI 初筛服务 — 简历智能筛选"""

    def __init__(self):
        self._pipeline = None
        self._aggregator = None

    @property
    def pipeline(self) -> PipelineAgent:
        if self._pipeline is None:
            self._pipeline = PipelineAgent.build_screening_pipeline()
        return self._pipeline

    @property
    def aggregator(self) -> AggregatorAgent:
        if self._aggregator is None:
            self._aggregator = AggregatorAgent(name="candidate_evaluator")
        return self._aggregator

    async def screen_resume(
        self,
        candidate_id: str,
        job_id: str,
        resume_text: str,
        job_requirements: str,
    ) -> dict:
        """运行完整 AI 初筛流水线。"""
        try:
            result = await self.pipeline.run({
                "resume_text": resume_text,
                "job_requirements": job_requirements,
            })
        except Exception as e:
            logger.warning("Pipeline evaluation failed, using fallback: %s", e)
            return {
                "pipeline_id": "",
                "candidate_id": candidate_id,
                "job_id": job_id,
                "overall_score": 0,
                "parsed_resume": {},
                "dimensions": {},
                "gate_passed": False,
                "needs_human_review": True,
                "strengths": [],
                "weaknesses": [],
                "recommendation": "评估不可用，请人工处理",
                "summary": f"AI 评估因底层错误不可用: {e}",
                "steps": [],
            }

        parsed = result.get("final_output", {}).get("parsed_resume", {})
        match = result.get("final_output", {}).get("match_result", {})
        gate = result.get("final_output", {}).get("gate_result", {})
        final_score = result.get("final_output", {}).get("final_score", match.get("overall_score", 0))
        gate_passed = result.get("final_output", {}).get("gate_passed", False)

        return {
            "pipeline_id": result.get("pipeline_id", ""),
            "candidate_id": candidate_id,
            "job_id": job_id,
            "overall_score": final_score,
            "parsed_resume": parsed,
            "dimensions": match,
            "gate_passed": gate_passed,
            "needs_human_review": gate.get("needs_human_review", False),
            "strengths": match.get("strengths", []),
            "weaknesses": match.get("weaknesses", []),
            "recommendation": match.get("recommendation", ""),
            "summary": gate.get("gate_summary", ""),
            "steps": result.get("steps", []),
        }

    async def multi_evaluate(
        self,
        candidate_info: str,
        dimensions: list[str] | None = None,
    ) -> dict:
        """多维度并行评估候选人。"""
        try:
            return await self.aggregator.run({
                "candidate_info": candidate_info,
                "dimensions": dimensions,
            })
        except Exception as e:
            logger.warning("Multi-evaluate failed, using fallback: %s", e)
            return {
                "error": "Evaluation unavailable",
                "evaluations": [],
                "summary": f"LLM 不可用，评估失败: {e}",
            }

    async def get_pipeline_progress(self, pipeline_id: str) -> dict:
        """获取流水线进度（简化版 — 后续可对接 RabbitMQ 异步）。"""
        return {
            "pipeline_id": pipeline_id,
            "status": "completed",
            "progress": 1.0,
            "current_step": "done",
            "steps": [],
        }
