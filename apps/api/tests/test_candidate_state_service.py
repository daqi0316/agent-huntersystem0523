from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.candidates import router as candidates_router
from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.models.candidate_state import RecruitmentCandidateState
from app.services.candidate_state import (
    CandidateStateService,
    CandidateStateTransitionError,
    get_triggered_actions,
)


class TestCandidateStateTransitions:
    def test_allows_expected_m1_path(self) -> None:
        service = CandidateStateService(MagicMock())

        service.validate_transition(
            RecruitmentCandidateState.NEW_APPLICATION,
            RecruitmentCandidateState.SCREENING,
        )
        service.validate_transition(
            RecruitmentCandidateState.SCREENING,
            RecruitmentCandidateState.SCREENING_PASSED,
        )
        service.validate_transition(
            RecruitmentCandidateState.SCREENING_PASSED,
            RecruitmentCandidateState.FIRST_INTERVIEW_PENDING,
        )

    def test_rejects_illegal_jump_to_offer(self) -> None:
        service = CandidateStateService(MagicMock())

        with pytest.raises(CandidateStateTransitionError) as exc:
            service.validate_transition(
                RecruitmentCandidateState.NEW_APPLICATION,
                RecruitmentCandidateState.OFFER_SENT,
            )

        assert "非法状态转换" in str(exc.value)
        assert "new_application -> offer_sent" in str(exc.value)

    def test_rejects_transition_from_terminal_state(self) -> None:
        service = CandidateStateService(MagicMock())

        with pytest.raises(CandidateStateTransitionError) as exc:
            service.validate_transition(
                RecruitmentCandidateState.SCREENING_REJECTED,
                RecruitmentCandidateState.FIRST_INTERVIEW_PENDING,
            )

        assert "终态 screening_rejected" in str(exc.value)

    def test_screening_passed_triggers_interview_preparation(self) -> None:
        actions = get_triggered_actions(RecruitmentCandidateState.SCREENING_PASSED)

        assert actions == [
            {"action": "generate_interview_guide", "agent": "interview_coordination_agent"},
            {"action": "match_interviewer", "agent": "interview_coordination_agent"},
        ]


def _make_app_with_org_override(db_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(candidates_router, prefix="/candidates")

    async def fake_get_db():
        yield db_mock

    async def fake_org_scoped_db(db=Depends(get_db)):
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[org_scoped_db] = fake_org_scoped_db
    return app


class TestCandidateStateApi:
    def test_transition_endpoint_success(self) -> None:
        db = MagicMock()
        app = _make_app_with_org_override(db)
        candidate = SimpleNamespace(id="c1")
        history = SimpleNamespace(
            id="h1",
            from_state=RecruitmentCandidateState.NEW_APPLICATION,
            to_state=RecruitmentCandidateState.SCREENING,
            triggered_actions=[],
        )
        service = MagicMock()
        service.transition = AsyncMock(return_value=(candidate, history))

        with patch("app.api.candidates.CandidateStateService", return_value=service):
            resp = TestClient(app).post(
                "/candidates/c1/state",
                json={"new_state": "screening", "reason": "开始初筛"},
            )

        assert resp.status_code == 200
        assert resp.json()["data"] == {
            "candidate_id": "c1",
            "from_state": "new_application",
            "to_state": "screening",
            "triggered_actions": [],
            "history_id": "h1",
        }
        service.transition.assert_awaited_once_with(
            candidate_id="c1",
            new_state=RecruitmentCandidateState.SCREENING,
            reason="开始初筛",
            operator_id="test-user-id",
            metadata=None,
        )

    def test_transition_endpoint_rejects_illegal_transition(self) -> None:
        db = MagicMock()
        app = _make_app_with_org_override(db)
        service = MagicMock()
        service.transition = AsyncMock(
            side_effect=CandidateStateTransitionError("非法状态转换：new_application -> offer_sent")
        )

        with patch("app.api.candidates.CandidateStateService", return_value=service):
            resp = TestClient(app).post(
                "/candidates/c1/state",
                json={"new_state": "offer_sent", "reason": "跳过流程"},
            )

        assert resp.status_code == 400
        assert "非法状态转换" in resp.json()["error"]
