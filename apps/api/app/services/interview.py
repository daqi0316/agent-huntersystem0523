"""面试安排服务 — DB 写入 + slot 冲突检测 + 评价管理。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import Interview, InterviewStatus, InterviewType
from app.models.interview_evaluation import InterviewEvaluation, InterviewRound, EvaluationVerdict


class InterviewService:
    """面试安排服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def schedule(
        self, candidate_id: str, job_id: str, slot: dict
    ) -> dict | None:
        """安排面试，含 slot 冲突检测。

        Args:
            candidate_id: 候选人 ID
            job_id: 职位 ID
            slot: {
                "application_id": str (optional),
                "type": "video" | "phone" | "onsite" | "technical",
                "scheduled_at": "2025-06-01T10:00:00Z",
                "duration_minutes": 60,
                "location": "...",
                "notes": "...",
            }

        Returns:
            dict: 面试详情，或 None 如果候选人不存在
        """
        interview_type_str = slot.get("type", "video")
        scheduled_at_str = slot.get("scheduled_at", "")
        duration = slot.get("duration_minutes", 60)
        location = slot.get("location", "")
        notes = slot.get("notes", "")
        application_id = slot.get("application_id", "")

        try:
            interview_type = InterviewType(interview_type_str)
        except ValueError:
            interview_type = InterviewType.VIDEO

        # Parse scheduled_at
        try:
            scheduled_at = datetime.fromisoformat(
                scheduled_at_str.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            scheduled_at = datetime.now(timezone.utc) + timedelta(days=1)

        scheduled_end = scheduled_at + timedelta(minutes=duration)

        # Check slot conflicts
        conflict_query = select(Interview).where(
            Interview.candidate_id == candidate_id,
            Interview.status.in_([
                InterviewStatus.SCHEDULED,
                InterviewStatus.CONFIRMED,
            ]),
        )
        conflict_result = await self.db.execute(conflict_query)
        existing = conflict_result.scalars().all()

        for interview in existing:
            if interview.scheduled_at:
                existing_end = interview.scheduled_at + timedelta(
                    minutes=interview.duration_minutes or 60
                )
                # Check overlap
                if scheduled_at < existing_end and scheduled_end > interview.scheduled_at:
                    return {
                        "error": True,
                        "message": "时间槽已被占用",
                        "conflict_id": interview.id,
                        "conflict_time": interview.scheduled_at.isoformat(),
                    }

        # Create interview
        interview = Interview(
            id=str(uuid.uuid4()),
            candidate_id=candidate_id,
            application_id=application_id or None,
            type=interview_type,
            status=InterviewStatus.SCHEDULED,
            scheduled_at=scheduled_at,
            duration_minutes=duration,
            location=location or None,
            notes=notes or None,
        )
        self.db.add(interview)
        await self.db.commit()
        await self.db.refresh(interview)

        return self._to_dict(interview)

    async def confirm(self, interview_id: str) -> dict | None:
        """确认面试。"""
        interview = await self._get_by_id(interview_id)
        if not interview:
            return None

        interview.status = InterviewStatus.CONFIRMED
        await self.db.commit()
        await self.db.refresh(interview)
        return self._to_dict(interview)

    async def cancel(self, interview_id: str) -> dict | None:
        """取消面试。"""
        interview = await self._get_by_id(interview_id)
        if not interview:
            return None

        interview.status = InterviewStatus.CANCELLED
        await self.db.commit()
        await self.db.refresh(interview)
        return self._to_dict(interview)

    async def complete(self, interview_id: str, feedback: str = "") -> dict | None:
        """标记面试为已完成，附带反馈。"""
        interview = await self._get_by_id(interview_id)
        if not interview:
            return None

        interview.status = InterviewStatus.COMPLETED
        if feedback:
            interview.feedback = feedback
        await self.db.commit()
        await self.db.refresh(interview)
        return self._to_dict(interview)

    async def list_by_candidate(
        self, candidate_id: str
    ) -> list[dict]:
        """获取候选人所有面试。"""
        result = await self.db.execute(
            select(Interview)
            .where(Interview.candidate_id == candidate_id)
            .order_by(Interview.scheduled_at.desc())
        )
        interviews = result.scalars().all()
        return [self._to_dict(iv) for iv in interviews]

    async def list_all(
        self, skip: int = 0, limit: int = 20, status: str | None = None
    ) -> tuple[list[dict], int]:
        """分页查询面试列表。"""
        from sqlalchemy import func

        query = select(Interview)
        count_query = select(func.count(Interview.id))

        if status:
            try:
                st = InterviewStatus(status)
                query = query.where(Interview.status == st)
                count_query = count_query.where(Interview.status == st)
            except ValueError:
                pass

        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(Interview.scheduled_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        interviews = result.scalars().all()
        return [self._to_dict(iv) for iv in interviews], total

    async def _get_by_id(self, interview_id: str) -> Interview | None:
        """根据 ID 获取面试记录。"""
        try:
            uuid.UUID(interview_id)
        except (ValueError, AttributeError):
            return None
        result = await self.db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        return result.scalar_one_or_none()

    async def get_evaluation(self, interview_id: str) -> InterviewEvaluation | None:
        result = await self.db.execute(
            select(InterviewEvaluation).where(InterviewEvaluation.interview_id == interview_id)
        )
        return result.scalar_one_or_none()

    async def save_evaluation(
        self,
        interview_id: str,
        round: InterviewRound = InterviewRound.R1,
        overall_score: float | None = None,
        verdict: EvaluationVerdict = EvaluationVerdict.CONSIDER,
        dimensions: dict | None = None,
        key_observations: str | None = None,
        red_flags: str | None = None,
        feedback: str | None = None,
    ) -> InterviewEvaluation:
        interview = await self._get_by_id(interview_id)
        if not interview:
            raise ValueError(f"Interview {interview_id} not found")

        evaluation = InterviewEvaluation(
            id=str(uuid.uuid4()),
            interview_id=interview_id,
            round=round,
            overall_score=overall_score,
            verdict=verdict,
            dimensions=json.dumps(dimensions, ensure_ascii=False) if dimensions else None,
            key_observations=key_observations,
            red_flags=red_flags,
            feedback=feedback,
        )
        self.db.add(evaluation)
        await self.db.commit()
        await self.db.refresh(evaluation)
        return evaluation

    async def list_evaluations_by_candidate(
        self, candidate_id: str
    ) -> list[dict]:
        from sqlalchemy import select
        stmt = (
            select(InterviewEvaluation)
            .join(Interview, InterviewEvaluation.interview_id == Interview.id)
            .where(Interview.candidate_id == candidate_id)
            .order_by(InterviewEvaluation.created_at.desc())
        )
        result = await self.db.execute(stmt)
        evals = result.scalars().all()
        return [self._eval_to_dict(e) for e in evals]

    @staticmethod
    def _eval_to_dict(e: InterviewEvaluation) -> dict:
        return {
            "id": e.id,
            "interview_id": e.interview_id,
            "round": e.round.value if e.round else "",
            "overall_score": e.overall_score,
            "verdict": e.verdict.value if e.verdict else "",
            "dimensions": json.loads(e.dimensions) if e.dimensions else {},
            "key_observations": e.key_observations or "",
            "red_flags": e.red_flags or "",
            "feedback": e.feedback or "",
            "created_at": e.created_at.isoformat() if e.created_at else "",
        }

    def _to_dict(self, interview: Interview) -> dict:
        return {
            "id": interview.id,
            "candidate_id": interview.candidate_id,
            "application_id": interview.application_id or "",
            "type": interview.type.value,
            "status": interview.status.value,
            "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else "",
            "duration_minutes": interview.duration_minutes or 60,
            "location": interview.location or "",
            "notes": interview.notes or "",
            "feedback": interview.feedback or "",
            "created_at": interview.created_at.isoformat() if interview.created_at else "",
            "updated_at": interview.updated_at.isoformat() if interview.updated_at else "",
        }
