from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.rejections import router as rejections_router
from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.models.application import ApplicationStatus
from app.models.candidate import CandidateStatus
from app.models.candidate_state import RecruitmentCandidateState
from app.models.rejection import RejectionReason
from app.schemas.rejection import CandidateRejectRequest, RejectionReasonCreate
from app.services.rejection import RejectionService


def _reason():
    reason = Mock(spec=RejectionReason)
    reason.id = "22222222-2222-2222-2222-222222222201"
    reason.code = "TECH_DEPTH_WEAK"
    reason.parent_id = None
    reason.category = "技术不够"
    reason.label = "技术深度不足"
    reason.description = "技术回答停留在表层"
    reason.severity = "medium"
    reason.stage_applicability = []
    reason.preventable_by = "screening"
    reason.is_active = True
    reason.created_at = datetime(2026, 6, 8, tzinfo=UTC)
    reason.updated_at = datetime(2026, 6, 8, tzinfo=UTC)
    return reason


def _record():
    record = SimpleNamespace()
    record.id = "33333333-3333-3333-3333-333333333301"
    record.candidate_id = "11111111-1111-1111-1111-111111111111"
    record.application_id = None
    record.job_profile_id = None
    record.reason_id = "22222222-2222-2222-2222-222222222201"
    record.reason_code = "TECH_DEPTH_WEAK"
    record.reason_category = "技术不够"
    record.primary_reason = "技术深度不足"
    record.stage = "screening"
    record.evidence = "无法解释 JVM 调优和分布式事务实战"
    record.detail = None
    record.reusable_for_future = False
    record.suggested_action = None
    record.metadata = None
    record.source = "human"
    record.confidence = None
    record.is_primary = True
    record.related_scorecard_submission_id = None
    record.related_dimension_id = None
    record.operator_id = "test-user-id"
    record.created_at = datetime(2026, 6, 8, tzinfo=UTC)
    return record


class TestRejectionService:
    async def test_create_reason_persists(self) -> None:
        db = AsyncMock()
        db.add = MagicMock(return_value=None)
        service = RejectionService(db)

        await service.create_reason(
            RejectionReasonCreate(
                code="TECH_DEPTH_WEAK",
                category="技术不够",
                label="技术深度不足",
            )
        )

        assert db.add.called
        assert db.commit.called
        assert db.refresh.called

    async def test_reject_candidate_updates_candidate_and_application(self) -> None:
        db = AsyncMock()
        db.add = MagicMock(return_value=None)
        candidate = SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            status=CandidateStatus.ACTIVE,
            recruitment_state=RecruitmentCandidateState.SCREENING,
        )
        application = SimpleNamespace(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            candidate_id=candidate.id,
            status=ApplicationStatus.SCREENING,
        )
        service = RejectionService(db)
        service._get_candidate = AsyncMock(return_value=candidate)
        service._get_application = AsyncMock(return_value=application)
        service.get_reason_by_code = AsyncMock(return_value=_reason())

        record = await service.reject_candidate(
            candidate_id=candidate.id,
            data=CandidateRejectRequest(
                reason_code="TECH_DEPTH_WEAK",
                stage="screening",
                evidence="无法解释 JVM 调优和分布式事务实战",
                application_id=application.id,
            ),
            operator_id="test-user-id",
        )

        assert candidate.status == CandidateStatus.FAILED
        assert candidate.recruitment_state == RecruitmentCandidateState.SCREENING_REJECTED
        assert application.status == ApplicationStatus.REJECTED
        assert record.reason_category == "技术不够"
        assert record.source.value == "human"
        assert record.is_primary is True
        assert db.add.called
        assert db.commit.called

    async def test_reject_candidate_rejects_unknown_reason(self) -> None:
        service = RejectionService(AsyncMock())
        service._get_candidate = AsyncMock(return_value=SimpleNamespace(id="c1"))
        service.get_reason_by_code = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as exc:
            await service.reject_candidate(
                candidate_id="c1",
                data=CandidateRejectRequest(
                    reason_code="MISSING",
                    stage="screening",
                    evidence="证据",
                ),
                operator_id="u1",
            )

        assert "淘汰原因不存在" in str(exc.value)


def _make_app(db_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(rejections_router, prefix="/rejections")

    async def fake_get_db():
        yield db_mock

    async def fake_org_scoped_db():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), db_mock

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[org_scoped_db] = fake_org_scoped_db
    return app


class TestRejectionApi:
    def test_list_reasons(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.list_reasons = AsyncMock(return_value=([_reason()], 1))

        with patch("app.api.rejections.RejectionService", return_value=svc):
            resp = TestClient(app).get("/rejections/reasons")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_create_reason_conflict(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.get_reason_by_code = AsyncMock(return_value=_reason())

        with patch("app.api.rejections.RejectionService", return_value=svc):
            resp = TestClient(app).post(
                "/rejections/reasons",
                json={
                    "code": "TECH_DEPTH_WEAK",
                    "category": "技术不够",
                    "label": "技术深度不足",
                },
            )

        assert resp.status_code == 409

    def test_reject_candidate_success(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.reject_candidate = AsyncMock(return_value=_record())

        with patch("app.api.rejections.RejectionService", return_value=svc):
            resp = TestClient(app).post(
                "/rejections/candidates/11111111-1111-1111-1111-111111111111/reject",
                json={
                    "reason_code": "TECH_DEPTH_WEAK",
                    "stage": "screening",
                    "evidence": "无法解释 JVM 调优和分布式事务实战",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["reason_code"] == "TECH_DEPTH_WEAK"

    def test_reject_candidate_missing_reason(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.reject_candidate = AsyncMock(side_effect=ValueError("淘汰原因不存在或已停用"))

        with patch("app.api.rejections.RejectionService", return_value=svc):
            resp = TestClient(app).post(
                "/rejections/candidates/c1/reject",
                json={"reason_code": "MISSING", "stage": "screening", "evidence": "证据"},
            )

        assert resp.status_code == 400

    def test_rejection_distribution(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.analytics = AsyncMock(
            return_value={
                "total": 1,
                "by_reason": [{"key": "TECH_DEPTH_WEAK", "label": "技术深度不足", "count": 1, "percentage": 1.0}],
                "by_stage": [{"key": "screening", "label": "screening", "count": 1, "percentage": 1.0}],
                "by_job_profile": [{"key": "unassigned", "label": "未关联岗位画像", "count": 1, "percentage": 1.0}],
                "by_preventable_by": [{"key": "screening", "label": "screening", "count": 1, "percentage": 1.0}],
            }
        )

        with patch("app.api.rejections.RejectionService", return_value=svc):
            resp = TestClient(app).get("/rejections/analytics/distribution")

        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 1


class TestRejectionAnalytics:
    async def test_analytics_groups_records(self) -> None:
        db = AsyncMock()
        record_result = MagicMock()
        record_result.scalars.return_value.all.return_value = [_record()]
        reason_result = MagicMock()
        reason_result.scalars.return_value.all.return_value = [_reason()]
        db.execute.side_effect = [record_result, reason_result]

        got = await RejectionService(db).analytics()

        assert got["total"] == 1
        assert got["by_reason"][0]["key"] == "TECH_DEPTH_WEAK"
        assert got["by_preventable_by"][0]["key"] == "screening"
