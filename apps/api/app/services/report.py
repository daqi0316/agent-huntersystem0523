"""评估报告服务 — LLM 生成 + keyword 降级。"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import get_llm_client
from app.models.application import Application, ApplicationStatus
from app.models.candidate import Candidate
from app.models.job_position import JobPosition

logger = logging.getLogger(__name__)

DIMENSION_NAMES = [
    "专业技能",
    "沟通能力",
    "经验匹配",
    "文化契合",
    "学习能力",
    "团队协作",
    "问题解决",
    "领导潜力",
]

DEFAULT_KEYWORD_SCORE = {
    "专业技能": 70,
    "沟通能力": 65,
    "经验匹配": 70,
    "文化契合": 60,
    "学习能力": 75,
    "团队协作": 65,
    "问题解决": 70,
    "领导潜力": 60,
}


class ReportService:
    """评估报告服务 — LLM 评估 + keyword 降级"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    async def generate_report(
        self, candidate_id: str, application_id: str
    ) -> dict:
        """生成候选人评估报告。

        Args:
            candidate_id: 候选人 ID
            application_id: 申请 ID

        Returns:
            dict: {
                "candidate_name": str,
                "job_title": str,
                "score_dimensions": [{"name": str, "score": int, "reason": str}],
                "overall_score": int,
                "summary": str,
                "llm_generated": bool,
            }
        """
        candidate, application, job = await self._load_data(
            candidate_id, application_id
        )

        # LLM generation with keyword fallback
        llm_success = False
        try:
            result = await self._llm_generate(candidate, job)
            llm_success = True
        except Exception as exc:
            logger.warning("LLM report generation failed, using fallback: %s", exc)
            result = self._keyword_generate(candidate, job)

        result["candidate_name"] = candidate.name
        result["job_title"] = job.title if job else ""
        result["llm_generated"] = llm_success

        # Update application match_score if available
        if application and llm_success:
            try:
                application.match_score = float(result["overall_score"]) / 100.0
                application.ai_summary = result.get("summary", "")
                await self.db.commit()
            except Exception:
                await self.db.rollback()

        return result

    async def get_report(self, report_id: str) -> dict:
        """获取报告（简化版 — 按需生成模式）。"""
        return {
            "report_id": report_id,
            "status": "available",
            "message": "报告按需生成，请使用 generate-report 端点",
        }

    async def _load_data(
        self, candidate_id: str, application_id: str
    ) -> tuple[Candidate | None, Application | None, JobPosition | None]:
        """加载候选人、申请、职位数据。"""
        c_result = await self.db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = c_result.scalar_one_or_none()

        a_result = await self.db.execute(
            select(Application).where(Application.id == application_id)
        )
        application = a_result.scalar_one_or_none()

        job = None
        if application:
            j_result = await self.db.execute(
                select(JobPosition).where(JobPosition.id == application.job_id)
            )
            job = j_result.scalar_one_or_none()

        return candidate, application, job

    async def _llm_generate(
        self, candidate: Candidate | None, job: JobPosition | None
    ) -> dict:
        """使用 LLM 生成评估报告。"""
        candidate_info = (
            f"候选人: {candidate.name or '未知'}\n"
            f"技能: {', '.join(candidate.skills or [])}\n"
            f"经验: {candidate.experience_years or 0} 年\n"
            f"当前职位: {candidate.current_title or '无'}\n"
            f"当前公司: {candidate.current_company or '无'}\n"
            f"简介: {candidate.summary or '无'}"
        )
        job_info = (
            f"职位: {job.title or '未知'}\n"
            f"部门: {job.department or '无'}\n"
            f"要求: {job.requirements or '无'}"
        )

        prompt = (
            "你是一个专业的招聘评估专家。请根据候选人信息和职位要求，"
            "生成一份详细的评估报告。\n\n"
            f"## 候选人信息\n{candidate_info}\n\n"
            f"## 职位信息\n{job_info}\n\n"
            "请对以下 8 个维度分别评分（0-100 分），并给出每个维度的评分理由，"
            "然后计算总分（各维度平均分），最后写一段综合评语。\n\n"
            "评分维度:\n"
            "1. 专业技能\n2. 沟通能力\n3. 经验匹配\n4. 文化契合\n"
            "5. 学习能力\n6. 团队协作\n7. 问题解决\n8. 领导潜力\n\n"
            "请严格按照以下 JSON 格式返回（不要包含其他文字）：\n"
            "{\n"
            '  "score_dimensions": [\n'
            '    {"name": "专业技能", "score": 85, "reason": "..."},\n'
            '    ...\n'
            "  ],\n"
            '  "overall_score": 78,\n'
            '  "summary": "综合评语..."\n'
            "}"
        )

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "你是一个专业的招聘评估专家。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        return self._parse_llm_response(response)

    def _parse_llm_response(self, response: str) -> dict:
        """解析 LLM 返回的 JSON。"""
        import json
        import re

        # Try to extract JSON from markdown fences
        json_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL
        )
        if json_match:
            response = json_match.group(1)

        try:
            data = json.loads(response)
            dimensions = data.get("score_dimensions", [])
            overall = data.get("overall_score", 0)
            summary = data.get("summary", "")
            return {
                "score_dimensions": dimensions,
                "overall_score": overall,
                "summary": summary,
            }
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse LLM response JSON, using fallback")
            return self._keyword_generate(None, None)

    def _keyword_generate(
        self, candidate: Candidate | None, job: JobPosition | None
    ) -> dict:
        """Keyword 降级评估。"""
        dimensions = []
        total = 0

        for name in DIMENSION_NAMES:
            score = DEFAULT_KEYWORD_SCORE.get(name, 65)

            # Skill match bonus
            if name == "专业技能" and candidate and candidate.skills:
                skill_count = len(candidate.skills)
                score = min(95, 60 + skill_count * 5)

            # Experience bonus
            if name == "经验匹配" and candidate and candidate.experience_years:
                score = min(95, 60 + candidate.experience_years * 3)

            dimensions.append({
                "name": name,
                "score": score,
                "reason": f"基于关键字分析，该维度评分为 {score}",
            })
            total += score

        overall = total // len(DIMENSION_NAMES)
        summary = (
            f"候选人综合评分 {overall} 分。"
            f"因 LLM 不可用，采用关键字降级评估。"
        )

        return {
            "score_dimensions": dimensions,
            "overall_score": overall,
            "summary": summary,
        }
