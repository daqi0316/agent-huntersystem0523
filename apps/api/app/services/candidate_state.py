from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.candidate_state import (
    CandidateStateHistory,
    RecruitmentCandidateState,
    TERMINAL_RECRUITMENT_STATES,
)


class CandidateStateTransitionError(ValueError):
    pass


ALLOWED_RECRUITMENT_TRANSITIONS: dict[
    RecruitmentCandidateState, set[RecruitmentCandidateState]
] = {
    RecruitmentCandidateState.NEW_APPLICATION: {RecruitmentCandidateState.SCREENING},
    RecruitmentCandidateState.SCREENING: {
        RecruitmentCandidateState.SCREENING_PASSED,
        RecruitmentCandidateState.SCREENING_REJECTED,
    },
    RecruitmentCandidateState.SCREENING_PASSED: {
        RecruitmentCandidateState.FIRST_INTERVIEW_PENDING
    },
    RecruitmentCandidateState.FIRST_INTERVIEW_PENDING: {
        RecruitmentCandidateState.FIRST_INTERVIEW_SCHEDULED
    },
    RecruitmentCandidateState.FIRST_INTERVIEW_SCHEDULED: {
        RecruitmentCandidateState.FIRST_INTERVIEW_FEEDBACK_PENDING,
        RecruitmentCandidateState.FIRST_INTERVIEW_REJECTED,
    },
    RecruitmentCandidateState.FIRST_INTERVIEW_FEEDBACK_PENDING: {
        RecruitmentCandidateState.FIRST_INTERVIEW_PASSED,
        RecruitmentCandidateState.FIRST_INTERVIEW_REJECTED,
    },
    RecruitmentCandidateState.FIRST_INTERVIEW_PASSED: {
        RecruitmentCandidateState.SECOND_INTERVIEW_PENDING
    },
    RecruitmentCandidateState.SECOND_INTERVIEW_PENDING: {
        RecruitmentCandidateState.SECOND_INTERVIEW_SCHEDULED
    },
    RecruitmentCandidateState.SECOND_INTERVIEW_SCHEDULED: {
        RecruitmentCandidateState.SECOND_INTERVIEW_FEEDBACK_PENDING,
        RecruitmentCandidateState.SECOND_INTERVIEW_REJECTED,
    },
    RecruitmentCandidateState.SECOND_INTERVIEW_FEEDBACK_PENDING: {
        RecruitmentCandidateState.SECOND_INTERVIEW_PASSED,
        RecruitmentCandidateState.SECOND_INTERVIEW_REJECTED,
    },
    RecruitmentCandidateState.SECOND_INTERVIEW_PASSED: {
        RecruitmentCandidateState.OFFER_NEGOTIATION
    },
    RecruitmentCandidateState.OFFER_NEGOTIATION: {RecruitmentCandidateState.OFFER_SENT},
    RecruitmentCandidateState.OFFER_SENT: {
        RecruitmentCandidateState.OFFER_ACCEPTED,
        RecruitmentCandidateState.OFFER_REJECTED,
    },
    RecruitmentCandidateState.OFFER_ACCEPTED: {
        RecruitmentCandidateState.ONBOARDING_PENDING
    },
    RecruitmentCandidateState.ONBOARDING_PENDING: {RecruitmentCandidateState.HIRED},
    RecruitmentCandidateState.HIRED: {RecruitmentCandidateState.PROBATION_TRACKING},
    RecruitmentCandidateState.PROBATION_TRACKING: {
        RecruitmentCandidateState.PROBATION_PASSED,
        RecruitmentCandidateState.PROBATION_REJECTED,
    },
}


def get_triggered_actions(new_state: RecruitmentCandidateState) -> list[dict]:
    actions_by_state: dict[RecruitmentCandidateState, list[dict]] = {
        RecruitmentCandidateState.SCREENING_PASSED: [
            {"action": "generate_interview_guide", "agent": "interview_coordination_agent"},
            {"action": "match_interviewer", "agent": "interview_coordination_agent"},
        ],
        RecruitmentCandidateState.FIRST_INTERVIEW_PASSED: [
            {"action": "schedule_next_round", "agent": "interview_coordination_agent"},
        ],
        RecruitmentCandidateState.SECOND_INTERVIEW_PASSED: [
            {"action": "prepare_offer_strategy", "agent": "compensation_agent"},
        ],
        RecruitmentCandidateState.OFFER_ACCEPTED: [
            {"action": "prepare_onboarding", "agent": "onboarding_agent"},
        ],
        RecruitmentCandidateState.HIRED: [
            {"action": "schedule_probation_checkins", "agent": "onboarding_agent"},
        ],
    }
    return actions_by_state.get(new_state, [])


class CandidateStateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_candidate(self, candidate_id: str) -> Candidate | None:
        result = await self.db.execute(select(Candidate).where(Candidate.id == candidate_id))
        return result.scalar_one_or_none()

    def validate_transition(
        self,
        current_state: RecruitmentCandidateState,
        new_state: RecruitmentCandidateState,
    ) -> None:
        if current_state in TERMINAL_RECRUITMENT_STATES:
            raise CandidateStateTransitionError(
                f"终态 {current_state.value} 不允许继续流转"
            )
        allowed = ALLOWED_RECRUITMENT_TRANSITIONS.get(current_state, set())
        if new_state not in allowed:
            allowed_values = sorted(state.value for state in allowed)
            raise CandidateStateTransitionError(
                f"非法状态转换：{current_state.value} -> {new_state.value}；"
                f"允许目标：{allowed_values}"
            )

    async def transition(
        self,
        candidate_id: str,
        new_state: RecruitmentCandidateState,
        reason: str,
        operator_id: str,
        metadata: dict | None = None,
    ) -> tuple[Candidate, CandidateStateHistory]:
        candidate = await self.get_candidate(candidate_id)
        if candidate is None:
            raise LookupError("候选人不存在")

        current_state = candidate.recruitment_state
        self.validate_transition(current_state, new_state)

        triggered_actions = get_triggered_actions(new_state)
        history = CandidateStateHistory(
            candidate_id=candidate.id,
            from_state=current_state,
            to_state=new_state,
            reason=reason,
            operator_id=operator_id,
            triggered_actions=triggered_actions,
            metadata_=metadata,
        )
        candidate.recruitment_state = new_state
        self.db.add(history)
        await self.db.commit()
        await self.db.refresh(candidate)
        await self.db.refresh(history)
        return candidate, history
