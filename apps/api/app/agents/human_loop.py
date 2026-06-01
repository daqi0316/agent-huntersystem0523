"""图7: Human-in-Loop 模式 — DB 持久化审批流程。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agents.base import BaseAgent
from app.core.database import AsyncSessionLocal
from app.llm import get_llm_client
from app.mcp.client import mcp_call_tool
from app.models.approval import ApprovalStatus
from app.services.approval_service import ApprovalService

logger = logging.getLogger(__name__)

INTERVIEW_SCHEDULE_PROMPT = """你是一位招聘协调员，负责安排面试时间。

候选人: {candidate_name}
职位: {job_title}
可用时间段: {available_slots}

请为面试安排推荐最佳时间段并生成面试邀请函。
输出 JSON（不要输出其他内容）:
{{
  "recommended_slot": "推荐的日期时间",
  "alternatives": ["备选1", "备选2"],
  "duration_minutes": 60,
  "interview_type": "技术面/行为面/综合面",
  "suggested_interviewers": ["面试官建议"],
  "invitation_draft": "面试邀请函正文"
}}"""


class HumanLoopAgent(BaseAgent):
    """图7: Human-in-Loop — 审批持久化到 DB，重启不丢失。"""

    def __init__(self, name: str = "human_loop"):
        super().__init__(name)
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    async def _with_db(self) -> ApprovalService:
        session = AsyncSessionLocal()
        return ApprovalService(session), session

    async def create_proposal(self, user_id: str, action_type: str, params: dict) -> dict:
        proposal = await self._generate_proposal(action_type, params)
        svc, session = await self._with_db()
        try:
            approval = await svc.create(
                user_id=user_id,
                action_type=action_type,
                proposal=proposal,
                params=params,
                target_type=params.get("target_type", ""),
                target_id=params.get("target_id", ""),
                candidate_email=params.get("candidate_email", "") or params.get("email", ""),
            )
            return {
                "approval_id": approval.id,
                "action_type": approval.action_type,
                "proposal": approval.proposal,
                "status": approval.status.value,
                "params": params,
                "created_at": approval.created_at.isoformat() if approval.created_at else "",
                "expires_at": approval.expires_at.isoformat() if approval.expires_at else "",
            }
        finally:
            await session.close()

    async def confirm(self, approval_id: str, user_id: str, approved: bool, feedback: str | None = None) -> dict:
        svc, session = await self._with_db()
        try:
            resolution = feedback or ""
            approval = await svc.resolve(approval_id, user_id, approved, resolution)
            if not approval:
                return {"error": "approval_not_found", "approval_id": approval_id}

            result = {
                "approval_id": approval.id,
                "action_type": approval.action_type,
                "status": approval.status.value,
                "proposal": approval.proposal,
                "feedback": feedback,
            }

            if approved and approval.action_type == "schedule_interview":
                record = {
                    "params": dict(approval.params or {}),
                    "proposal": dict(approval.proposal or {}),
                    "execution": {},
                }
                await self._execute_schedule_actions(record)
                result["execution"] = record.get("execution", {})

            return result
        finally:
            await session.close()

    async def run(self, input_data: dict) -> dict:
        action_type = input_data.get("action_type", "schedule_interview")
        params = input_data.get("params", {})
        user_id = input_data.get("user_id", "")

        if input_data.get("confirm"):
            return await self.confirm(
                input_data["approval_id"],
                user_id or input_data.get("resolver_id", ""),
                input_data.get("approved", False),
                input_data.get("feedback"),
            )

        proposal = await self.create_proposal(user_id, action_type, params)
        return {
            "agent": self.name,
            "status": "awaiting_approval",
            "approval": proposal,
        }

    async def _generate_proposal(self, action_type: str, params: dict) -> dict:
        if action_type == "schedule_interview":
            return await self._generate_interview_proposal(params)
        elif action_type == "send_email":
            return self._generate_email_draft(params)
        return {"action": action_type, "params": params}

    async def _generate_interview_proposal(self, params: dict) -> dict:
        messages = [
            {"role": "system", "content": INTERVIEW_SCHEDULE_PROMPT.format(
                candidate_name=params.get("candidate_name", "候选人"),
                job_title=params.get("job_title", "职位"),
                available_slots=str(params.get("available_slots", ["无可用时间段"])),
            )},
            {"role": "user", "content": "请生成面试安排建议。"},
        ]
        result = await self.llm.chat(messages, temperature=0.4, max_tokens=1024)
        try:
            json_match = re.search(r"\{.*\}", result, re.DOTALL)
            text = json_match.group() if json_match else result
            parsed = json.loads(
                text.strip().removeprefix("```json").removesuffix("```").strip()
            )
        except (json.JSONDecodeError, AttributeError):
            parsed = {"raw": result, "error": "parse_failed"}
        return parsed

    @staticmethod
    def _generate_email_draft(params: dict) -> dict:
        return {
            "to": params.get("to", ""),
            "subject": params.get("subject", ""),
            "body": params.get("body", ""),
        }

    async def _execute_schedule_actions(self, record: dict) -> None:
        params = record.get("params", {})
        proposal = record.get("proposal", {})
        candidate_email = params.get("candidate_email", "") or params.get("email", "")
        candidate_name = params.get("candidate_name", "候选人")
        job_title = params.get("job_title", "面试")
        slot = proposal.get("recommended_slot", "") if isinstance(proposal, dict) else ""
        duration = proposal.get("duration_minutes", 60) if isinstance(proposal, dict) else 60
        invitation = proposal.get("invitation_draft", "") if isinstance(proposal, dict) else ""

        execution_log: list[dict] = []
        if candidate_email:
            try:
                email_result = await mcp_call_tool(
                    url="http://localhost:8888/api/v1/tools/email/send",
                    tool_name="send_email",
                    arguments={
                        "to": candidate_email,
                        "subject": f"面试邀请: {job_title}",
                        "body": invitation or f"您好 {candidate_name}，我们邀请您参加 {job_title} 的面试。",
                    },
                )
                execution_log.append({"tool": "email", "status": "sent", "result": str(email_result)[:200]})
            except Exception as e:
                execution_log.append({"tool": "email", "status": "failed", "error": str(e)[:200]})

        if candidate_email and slot:
            try:
                start_dt = datetime.fromisoformat(slot) if isinstance(slot, str) else datetime.now(UTC)
                end_dt = start_dt + timedelta(minutes=duration)
                calendar_result = await mcp_call_tool(
                    url="http://localhost:8888/api/v1/tools/calendar/book",
                    tool_name="book_calendar",
                    arguments={
                        "title": f"面试: {candidate_name} - {job_title}",
                        "start_time": start_dt.isoformat(),
                        "end_time": end_dt.isoformat(),
                        "attendee_email": candidate_email,
                        "description": invitation or f"{candidate_name} 的 {job_title} 面试",
                    },
                )
                execution_log.append({"tool": "calendar", "status": "booked", "result": str(calendar_result)[:200]})
            except Exception as e:
                execution_log.append({"tool": "calendar", "status": "failed", "error": str(e)[:200]})

        record["execution"] = {"log": execution_log, "completed_at": datetime.now(UTC).isoformat()}

    async def get_pending_count(self) -> int:
        svc, session = await self._with_db()
        try:
            items = await svc.list_pending()
            return len(items)
        finally:
            await session.close()

    async def get_pending_proposals(self) -> list[dict]:
        svc, session = await self._with_db()
        try:
            return await svc.list_pending()
        finally:
            await session.close()

    async def get_approval_history(self, limit: int = 50) -> list[dict]:
        svc, session = await self._with_db()
        try:
            return await svc.list_history(limit=limit)
        finally:
            await session.close()

    async def get_approval_status(self, approval_id: str) -> dict | None:
        svc, session = await self._with_db()
        try:
            approval = await svc.get(approval_id)
            if not approval:
                return None
            return {"approval_id": approval.id, "status": approval.status.value, "found_in": "db"}
        finally:
            await session.close()

    async def _pending_purge_all(self) -> None:
        logger.warning("Emergency stop: cancelling all pending approvals")
        async with AsyncSessionLocal() as db:
            from sqlalchemy import update as sa_update, and_
            stmt = (
                sa_update(type("tmp", (), {"__tablename__": "approvals"})())
                .where(type("tmp", (), {"status": "pending"})())
            )
            await db.execute(stmt)
            await db.commit()
