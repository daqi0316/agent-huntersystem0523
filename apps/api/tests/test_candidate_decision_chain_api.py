from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.candidates import router as candidates_router
from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.models.application import ApplicationStatus
from app.models.candidate import CandidateStatus
from app.models.candidate_state import RecruitmentCandidateState
from app.models.interview import InterviewStatus, InterviewType
from app.models.interview_evaluation import EvaluationVerdict, InterviewRound


def _make_app_with_org_override(db_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(candidates_router, prefix="/candidates")

    async def fake_get_db():
        yield db_mock

    async def fake_org_scoped_db():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), db_mock

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[org_scoped_db] = fake_org_scoped_db
    return app


def _execute_result(items: list[object]):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _candidate():
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        name="张三",
        status=CandidateStatus.ACTIVE,
        recruitment_state=RecruitmentCandidateState.SCREENING_PASSED,
    )


def _java_p7_profile():
    return SimpleNamespace(
        id="p1",
        code="Java_P7",
        title="Java P7",
        level="P7",
        hard_requirements=["5年 Java"],
        soft_requirements=["跨团队协作"],
        evaluation_dimensions=[{"dimension": "技术深度", "weight": 0.3}],
        interview_focus=["高并发细节"],
    )


class TestCandidateDecisionChainApi:
    def test_decision_chain_empty_sections(self) -> None:
        db = AsyncMock()
        db.execute.side_effect = [
            _execute_result([]),
            _execute_result([]),
            _execute_result([]),
            _execute_result([]),
            _execute_result([]),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        app = _make_app_with_org_override(db)
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=_candidate())

        with patch("app.api.candidates.CandidateService", return_value=service):
            resp = TestClient(app).get("/candidates/11111111-1111-1111-1111-111111111111/decision-chain")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["candidate"]["recruitment_state"] == "screening_passed"
        assert data["state_history"] == []
        assert data["job_profiles"] == []
        assert data["rejections"] == []
        assert data["missing_sections"] == [
            "state_history",
            "job_profiles",
            "rejections",
            "interviews",
            "interview_feedback",
        ]

    def test_decision_chain_uses_java_p7_fallback_profile(self) -> None:
        db = AsyncMock()
        db.execute.side_effect = [
            _execute_result([]),
            _execute_result([]),
            _execute_result([]),
            _execute_result([]),
            _execute_result([]),
            MagicMock(scalar_one_or_none=MagicMock(return_value=_java_p7_profile())),
        ]
        app = _make_app_with_org_override(db)
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=_candidate())

        with patch("app.api.candidates.CandidateService", return_value=service):
            resp = TestClient(app).get("/candidates/11111111-1111-1111-1111-111111111111/decision-chain")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["job_profiles"][0]["code"] == "Java_P7"
        assert "job_profiles" not in data["missing_sections"]

    def test_decision_chain_populated(self) -> None:
        created_at = datetime(2026, 6, 8, tzinfo=UTC)
        history = SimpleNamespace(
            id="h1",
            from_state=RecruitmentCandidateState.SCREENING,
            to_state=RecruitmentCandidateState.SCREENING_PASSED,
            reason="初筛通过",
            operator_id="test-user-id",
            triggered_actions=[{"action": "generate_interview_guide"}],
            metadata_={"source": "test"},
            created_at=created_at,
        )
        application = SimpleNamespace(
            id="a1",
            job_id="j1",
            status=ApplicationStatus.SCREENING,
            match_score=88.0,
            ai_summary="匹配 Java P7",
            created_at=created_at,
        )
        job = SimpleNamespace(id="j1", title="Java 高级工程师")
        interview = SimpleNamespace(
            id="i1",
            application_id="a1",
            type=InterviewType.TECHNICAL,
            status=InterviewStatus.SCHEDULED,
            scheduled_at=created_at,
            feedback=None,
        )
        feedback = SimpleNamespace(
            id="f1",
            interview_id="i1",
            round=InterviewRound.R2,
            overall_score=4.0,
            verdict=EvaluationVerdict.HIRE,
            dimensions='[{"dimension":"技术深度","score":4}]',
            key_observations="分布式经验扎实",
            red_flags=None,
            feedback="建议通过",
            created_at=created_at,
        )
        scorecard = SimpleNamespace(
            id="s1",
            interview_id="i1",
            candidate_id="11111111-1111-1111-1111-111111111111",
            application_id="a1",
            scorecard_template_id="t1",
            interviewer_id="test-user-id",
            overall_score=4.2,
            verdict=EvaluationVerdict.HIRE,
            summary="结构化评分建议通过",
            risk_flags=[],
            submitted_at=created_at,
        )
        dimension_score = SimpleNamespace(
            id="ds1",
            submission_id="s1",
            dimension_id="d1",
            score=4,
            evidence="能解释 JVM 调优取舍",
            confidence=0.8,
        )
        scorecard_dimension = SimpleNamespace(id="d1", name="技术深度")
        scorecard_template = SimpleNamespace(
            id="t1",
            name="Java P7 技术面评分卡",
            profile_version_id="v1",
        )
        rejection = SimpleNamespace(
            id="r1",
            reason_code="STABILITY_RISK",
            reason_category="稳定性",
            primary_reason="稳定性风险",
            stage="screening",
            evidence="三年三跳",
            detail=None,
            reusable_for_future=True,
            suggested_action="追问离职原因",
            job_profile_id="p1",
            application_id="a1",
            created_at=created_at,
        )
        profile = _java_p7_profile()
        db = AsyncMock()
        db.execute.side_effect = [
            _execute_result([history]),
            _execute_result([application]),
            _execute_result([job]),
            _execute_result([interview]),
            _execute_result([feedback]),
            _execute_result([scorecard]),
            _execute_result([dimension_score]),
            _execute_result([scorecard_dimension]),
            _execute_result([scorecard_template]),
            _execute_result([rejection]),
            _execute_result([]),
            _execute_result([profile]),
        ]
        app = _make_app_with_org_override(db)
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=_candidate())

        with patch("app.api.candidates.CandidateService", return_value=service):
            resp = TestClient(app).get("/candidates/11111111-1111-1111-1111-111111111111/decision-chain")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["state_history"][0]["to_state"] == "screening_passed"
        assert data["applications"][0]["job_title"] == "Java 高级工程师"
        assert data["job_profiles"][0]["code"] == "Java_P7"
        assert data["interviews"][0]["type"] == "technical"
        assert data["interview_feedback"][0]["verdict"] == "hire"
        assert data["scorecards"][0]["overall_score"] == 4.2
        assert data["scorecards"][0]["scorecard_template_name"] == "Java P7 技术面评分卡"
        assert data["scorecards"][0]["profile_version_id"] == "v1"
        assert data["scorecards"][0]["dimension_scores"][0]["evidence"] == "能解释 JVM 调优取舍"
        assert data["rejections"][0]["evidence"] == "三年三跳"
        assert data["missing_sections"] == []
