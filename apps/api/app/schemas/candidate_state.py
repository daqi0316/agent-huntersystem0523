from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.candidate_state import RecruitmentCandidateState


class CandidateStateTransitionRequest(BaseModel):
    new_state: RecruitmentCandidateState
    reason: str = Field(..., min_length=1, max_length=2000)
    metadata: dict | None = None


class CandidateStateHistoryRead(BaseModel):
    id: str
    candidate_id: str
    from_state: RecruitmentCandidateState | None
    to_state: RecruitmentCandidateState
    reason: str
    operator_id: str
    triggered_actions: list[dict]
    metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CandidateStateTransitionRead(BaseModel):
    candidate_id: str
    from_state: RecruitmentCandidateState
    to_state: RecruitmentCandidateState
    triggered_actions: list[dict]
    history: CandidateStateHistoryRead
