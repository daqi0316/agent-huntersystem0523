"""主动推荐服务 — 候选人-职位匹配引擎 + 通知管理。

核心流程:
  1. 定时扫描所有 active 职位和 active 候选人
  2. 对每对未产生申请的 (candidate, job) 计算匹配分
  3. 超过阈值的生成 Recommendation 记录
  4. 用户通过 API 消费推荐 (列表/忽略)

匹配算法 (MVP):
  - 技能关键词重叠: candidate.skills ∩ job.requirements 分词
  - 经验年数匹配
  - 综合评分 0-100
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.candidate import Candidate, CandidateStatus
from app.models.job_position import JobPosition, JobStatus
from app.models.recommendation import Recommendation, RecommendationType

logger = logging.getLogger(__name__)

# ── 推荐配置 ──

MATCH_SCORE_THRESHOLD = 50  # 最低匹配分（低于此不生成推荐）
MAX_RECOMMENDATIONS_PER_RUN = 50  # 每次扫描最多生成 N 条
TOP_K_PER_JOB = 5  # 每个职位最多推荐 K 个候选人
SCAN_DUPLICATE_WINDOW_HOURS = 72  # 相同 pair 在此时间内不重复推荐

PROACTIVE_SYSTEM_PROMPT = (
    "你是一个招聘系统的主动推荐助手。根据公司当前 active 职位和候选人池，"
    "找到最值得推荐的候选人-职位匹配，给出推荐理由。"
    "输出 JSON 数组，每项包含: candidate_id, job_id, score(0-100), reason。"
)


class RecommendationService:
    """主动推荐服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 匹配引擎 ──

    async def generate_recommendations(self, user_id: str) -> list[Recommendation]:
        """为指定用户生成推荐: 扫描 active 职位 + active 候选人 → 计算匹配。"""
        jobs = await self._get_active_jobs()
        if not jobs:
            logger.info("No active jobs found, skipping recommendation generation")
            return []

        candidates = await self._get_eligible_candidates()
        if not candidates:
            logger.info("No eligible candidates found, skipping recommendation generation")
            return []

        created: list[Recommendation] = []
        for job in jobs:
            job_candidates = await self._rank_candidates_for_job(job, candidates, user_id)
            for candidate_id, score, reason in job_candidates[:TOP_K_PER_JOB]:
                if score < MATCH_SCORE_THRESHOLD:
                    continue

                rec = Recommendation(
                    user_id=user_id,
                    type=RecommendationType.CANDIDATE_JOB_MATCH,
                    title=f"候选人匹配: {job.title}",
                    description=f"为职位「{job.title}」推荐了一名候选人",
                    candidate_id=candidate_id,
                    job_id=job.id,
                    score=score,
                    reason=reason,
                )
                self.db.add(rec)
                created.append(rec)

                if len(created) >= MAX_RECOMMENDATIONS_PER_RUN:
                    break

            if len(created) >= MAX_RECOMMENDATIONS_PER_RUN:
                break

        if created:
            await self.db.commit()
            logger.info("Generated %d recommendations for user %s", len(created), user_id)

        return created

    async def _get_active_jobs(self) -> list[JobPosition]:
        """获取所有 active 职位（含 requirements 不为空的优先）。"""
        stmt = (
            select(JobPosition)
            .where(JobPosition.status == JobStatus.ACTIVE)
            .order_by(JobPosition.created_at.desc())
        )
        result = await self.db.execute(stmt)
        jobs = list(result.scalars().all())
        # 有 requirements 的排前面
        jobs.sort(key=lambda j: (1 if j.requirements else 0), reverse=True)
        return jobs

    async def _get_eligible_candidates(self) -> list[Candidate]:
        """获取适合推荐的候选人（active 且未被拒绝的）。"""
        stmt = (
            select(Candidate)
            .where(
                Candidate.status.in_([
                    CandidateStatus.ACTIVE,
                    CandidateStatus.PENDING_EVAL,
                    CandidateStatus.EVALUATED,
                ]),
            )
            .order_by(Candidate.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _has_existing_application(self, candidate_id: str, job_id: str) -> bool:
        """检查候选人是否已对该职位提交过申请。"""
        from app.models.application import Application
        stmt = select(Application).where(
            and_(
                Application.candidate_id == candidate_id,
                Application.job_id == job_id,
            ),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _has_recent_recommendation(self, candidate_id: str, job_id: str, hours: int = 72) -> bool:
        """检查是否在时间窗口内已推荐过该 pair。"""
        from sqlalchemy import func as sa_func
        cutoff = datetime.now(timezone.utc)
        stmt = select(Recommendation).where(
            and_(
                Recommendation.candidate_id == candidate_id,
                Recommendation.job_id == job_id,
                Recommendation.type == RecommendationType.CANDIDATE_JOB_MATCH,
                Recommendation.created_at >= cutoff,
            ),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _rank_candidates_for_job(
        self,
        job: JobPosition,
        candidates: list[Candidate],
        user_id: str,
    ) -> list[tuple[str, int, str]]:
        """为单个职位计算候选人的匹配分并排序。"""
        scored: list[tuple[str, int, str]] = []

        for c in candidates:
            # 跳过已有申请的
            if await self._has_existing_application(c.id, job.id):
                continue
            # 跳过近期已推荐过的
            if await self._has_recent_recommendation(c.id, job.id):
                continue

            score, reason = await self._compute_match(job, c)
            if score >= MATCH_SCORE_THRESHOLD:
                scored.append((c.id, score, reason))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    async def _compute_match(self, job: JobPosition, candidate: Candidate) -> tuple[int, str]:
        """计算候选人与职位的匹配分和理由(不依赖 LLM, 纯规则)。"""
        if not candidate.skills or not job.requirements:
            return 0, ""

        # ── 1. 技能匹配 ──
        req_keywords = self._extract_keywords(job.requirements)
        candidate_skills_lower = {s.strip().lower() for s in (candidate.skills or []) if s.strip()}

        if not req_keywords:
            return 0, ""

        matched_keywords = [kw for kw in req_keywords if kw.lower() in candidate_skills_lower]
        missing_keywords = [kw for kw in req_keywords if kw.lower() not in candidate_skills_lower]

        skill_score = int(len(matched_keywords) / len(req_keywords) * 70)  # 技能占 70 分

        # ── 2. 经验匹配 ──
        exp_score = 0
        # 尝试从 requirements 中提取经验要求
        exp_req = self._extract_experience_requirement(job.requirements)
        if exp_req is not None and candidate.experience_years is not None:
            if candidate.experience_years >= exp_req:
                exp_score = 20  # 经验达标
            elif candidate.experience_years >= exp_req * 0.7:
                exp_score = 10  # 经验接近
        elif candidate.experience_years is not None and candidate.experience_years >= 2:
            exp_score = 15  # 无明确要求但候选人经验≥2年

        total = min(skill_score + exp_score, 100)

        # ── 生成理由 ──
        reason_parts = []
        if matched_keywords:
            reason_parts.append(f"匹配技能: {', '.join(matched_keywords[:5])}")
        if missing_keywords and len(missing_keywords) <= len(req_keywords) * 0.5:
            reason_parts.append(f"少许差距: {', '.join(missing_keywords[:3])}")
        if exp_req and candidate.experience_years is not None:
            reason_parts.append(f"{candidate.experience_years}年经验({'满足' if candidate.experience_years >= exp_req else '接近'}要求{exp_req}年)")
        elif candidate.experience_years is not None:
            reason_parts.append(f"{candidate.experience_years}年经验")
        if candidate.current_company:
            reason_parts.append(f"来自 {candidate.current_company}")
        if candidate.current_title:
            reason_parts.append(f"现任 {candidate.current_title}")

        reason = "；".join(reason_parts[:4]) if reason_parts else "综合匹配"
        return total, reason

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """从职位要求中提取关键词: 英文技能词 + 中文技术词。"""
        text = text.lower()
        # 常见编程/技术关键词
        common_skills = {
            "python", "java", "javascript", "typescript", "golang", "rust", "c++", "c#",
            "react", "vue", "angular", "node.js", "node", "express", "django", "flask",
            "fastapi", "spring", "springboot", "sqlalchemy", "sql", "postgresql", "mysql",
            "redis", "mongodb", "docker", "kubernetes", "k8s", "aws", "gcp", "azure",
            "git", "ci/cd", "pytest", "jest", "machine learning", "deep learning",
            "tensorflow", "pytorch", "nlp", "llm", "rag", "data analysis",
            "rest api", "graphql", "grpc", "microservices", "kafka", "rabbitmq",
            "html", "css", "sass", "tailwind", "next.js", "nuxt.js", "flutter",
            "swift", "kotlin", "android", "ios", "react native",
        }
        found = set()
        for skill in common_skills:
            if skill in text:
                found.add(skill)

        # 也提取中文技术词（简单的模式匹配）
        cn_patterns = re.findall(r'[（(]?([\u4e00-\u9fff]{2,6}(?:开发|设计|框架|平台|系统|算法|分析|运维))[）)]?', text)
        for p in cn_patterns:
            found.add(p)

        return sorted(found)

    @staticmethod
    def _extract_experience_requirement(text: str) -> int | None:
        """从职位描述中提取经验年数要求。"""
        patterns = [
            r"(\d+)[\-~到至](\d+)\s*年",
            r"(\d+)\s*年以上",
            r"至少\s*(\d+)\s*年",
            r"(\d+)\+?\s*years?",
        ]
        for pat in patterns:
            m = re.search(pat, text.lower())
            if m:
                if m.lastindex == 2:
                    return int(m.group(1))  # 取下限
                return int(m.group(1))
        return None

    # ── 推荐 CRUD ──

    async def list_recommendations(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> list[Recommendation]:
        """列出用户的推荐。"""
        stmt = (
            select(Recommendation)
            .where(
                Recommendation.user_id == user_id,
                Recommendation.dismissed == False,  # noqa: E712
            )
        )
        if unread_only:
            stmt = stmt.where(Recommendation.read == False)  # noqa: E712

        stmt = stmt.order_by(Recommendation.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_unread(self, user_id: str) -> int:
        """统计未读推荐数量。"""
        from sqlalchemy import func as sa_func
        stmt = select(sa_func.count()).select_from(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.read == False,  # noqa: E712
            Recommendation.dismissed == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def mark_read(self, recommendation_id: str, user_id: str) -> bool:
        """标记推荐为已读。"""
        result = await self.db.execute(
            select(Recommendation).where(
                Recommendation.id == recommendation_id,
                Recommendation.user_id == user_id,
            ),
        )
        rec = result.scalar_one_or_none()
        if not rec:
            return False
        rec.read = True
        await self.db.commit()
        return True

    async def mark_all_read(self, user_id: str) -> int:
        """标记用户的所有推荐为已读。返回更新的条数。"""
        from sqlalchemy import update
        stmt = (
            update(Recommendation)
            .where(
                Recommendation.user_id == user_id,
                Recommendation.read == False,  # noqa: E712
                Recommendation.dismissed == False,  # noqa: E712
            )
            .values(read=True)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount or 0

    async def dismiss(self, recommendation_id: str, user_id: str) -> bool:
        """忽略一条推荐。"""
        result = await self.db.execute(
            select(Recommendation).where(
                Recommendation.id == recommendation_id,
                Recommendation.user_id == user_id,
            ),
        )
        rec = result.scalar_one_or_none()
        if not rec:
            return False
        rec.dismissed = True
        await self.db.commit()
        return True
