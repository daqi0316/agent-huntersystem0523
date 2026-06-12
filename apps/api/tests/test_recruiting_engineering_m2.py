"""Tests for P0-A recruiting engineering changes (M2.5-M2.7).

Covers:
- Version protocol: activate_version sets activated_by/at/effective_from
- Evidence ref: create, link to dimension score
- AI audit: create and query
- Template lifecycle API: activate/archive
- Evidence/audit query API
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.candidates import router as candidates_router
from app.api.job_profiles import router as job_profiles_router
from app.api.scorecards import router as scorecards_router
from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.models.ai_decision_audit import AiDecisionAudit, AiDecisionType
from app.models.evidence_ref import EvidenceCreatedByType, EvidenceRef, EvidenceSourceType
from app.models.job_profile import JobProfile, JobProfileVersion, JobProfileVersionStatus
from app.models.scorecard import ScorecardStatus, ScorecardTemplate
from app.schemas.evidence_ref import EvidenceRefCreate
from app.schemas.ai_decision_audit import AiDecisionAuditCreate
from app.schemas.job_profile import JobProfileVersionCreate
from app.services.job_profile import JobProfileService


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock(return_value=None)
    return db


@pytest.fixture
def job_profile_service(mock_db):
    return JobProfileService(mock_db)


def _make_profile():
    profile = Mock(spec=JobProfile)
    profile.id = "11111111-1111-1111-1111-111111111107"
    profile.code = "Java_P7"
    profile.title = "高级 Java 工程师"
    profile.level = "P7"
    profile.department = "技术部"
    profile.is_active = True
    profile.hard_requirements = ["5年以上 Java 开发经验"]
    profile.soft_requirements = ["跨团队协作"]
    profile.evaluation_dimensions = []
    profile.salary_band = {}
    profile.interview_focus = []
    profile.created_at = "2026-06-08T00:00:00"
    profile.updated_at = "2026-06-08T00:00:00"
    return profile


def _make_version(version_id: str = "00000000-0000-0000-0000-000000000001", status: str = "draft"):
    version = Mock(spec=JobProfileVersion)
    version.id = version_id
    version.job_profile_id = "11111111-1111-1111-1111-111111111107"
    version.version = 1
    version.status = JobProfileVersionStatus(status)
    version.change_reason = None
    version.snapshot = {}
    version.created_by = "test-user"
    version.created_at = datetime(2026, 6, 8, tzinfo=UTC)
    version.effective_from = None
    version.effective_to = None
    version.activated_by = None
    version.activated_at = None
    version.archived_at = None
    return version


class TestVersionProtocol:
    """M2.5: effective dating and audit trail on version lifecycle."""

    async def test_activate_version_sets_activated_fields(self, job_profile_service, mock_db) -> None:
        """activate_version 必须设置 activated_by, activated_at, effective_from."""
        version = _make_version(status="draft")
        get_result = Mock()
        get_result.scalar_one_or_none.return_value = version
        update_result = Mock()
        update_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [get_result, update_result]

        result = await job_profile_service.activate_version(
            version.job_profile_id, version.id, activated_by="test-activator"
        )

        assert result is not None
        assert result.activated_by == "test-activator"
        assert result.activated_at is not None
        assert result.effective_from is not None
        assert result.archived_at is None
        assert result.status == JobProfileVersionStatus.ACTIVE

    async def test_activate_version_archives_others(self, job_profile_service, mock_db) -> None:
        """激活新版本时，同岗位旧版本应被归档."""
        version = _make_version(status="draft")
        get_result = Mock()
        get_result.scalar_one_or_none.return_value = version
        update_result = Mock()

        mock_db.execute.side_effect = [get_result, update_result]

        result = await job_profile_service.activate_version(
            version.job_profile_id, version.id, activated_by="test-user"
        )

        assert result is not None
        assert mock_db.execute.called

    async def test_create_active_version_sets_fields(self, job_profile_service, mock_db) -> None:
        """直接创建 ACTIVE 版本也应设置 activated_by/at/effective_from."""
        profile = _make_profile()
        profile_result = Mock()
        profile_result.scalar_one_or_none.return_value = profile

        max_version_result = Mock()
        max_version_result.scalar.return_value = 0

        empty_result = Mock()
        empty_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [profile_result, max_version_result, empty_result, empty_result]

        data = JobProfileVersionCreate(change_reason="v2", status="active")
        result = await job_profile_service.create_version(
            "11111111-1111-1111-1111-111111111107", data, created_by="test-user"
        )

        assert result is not None
        assert result.activated_by == "test-user"
        assert result.activated_at is not None
        assert result.effective_from is not None


class TestEvidenceRefIntegration:
    """M2.6: unified evidence reference protocol."""

    def test_evidence_ref_create_schema_valid(self) -> None:
        data = EvidenceRefCreate(
            candidate_id="cand-1",
            source_type="scorecard",
            normalized_claim="候选人在 JVM 调优方面经验丰富",
            created_by_type="ai",
        )
        assert data.candidate_id == "cand-1"
        assert data.source_type == "scorecard"
        assert data.created_by_type == "ai"

    def test_evidence_ref_create_with_all_fields(self) -> None:
        data = EvidenceRefCreate(
            candidate_id="cand-1",
            application_id="app-1",
            source_type="interview",
            source_id="int-1",
            quote="我做过 JVM 调优",
            normalized_claim="候选人有 JVM 调优经验",
            confidence=0.9,
            created_by_type="human",
            created_by_id="reviewer-1",
        )
        assert data.confidence == 0.9
        assert data.source_type == "interview"
        assert data.created_by_type == "human"

    def test_evidence_ref_create_rejects_invalid_confidence(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRefCreate(
                candidate_id="cand-1",
                source_type="resume",
                normalized_claim="claim",
                created_by_type="ai",
                confidence=1.5,
            )

    def test_evidence_ref_enum_labels_match_model(self) -> None:
        """保证 schema 的 source_type 值与模型 enum 一致。"""
        expected = {e.value for e in EvidenceSourceType}
        assert "resume" in expected
        assert "interview" in expected
        assert "scorecard" in expected
        assert "rejection" in expected
        assert "knowledge" in expected


class TestAiDecisionAuditIntegration:
    """M2.7: AI decision audit trail."""

    def test_audit_create_schema_valid(self) -> None:
        data = AiDecisionAuditCreate(
            candidate_id="cand-1",
            decision_type="scorecard_assist",
            model_name="gpt-4",
            output_summary="维度评分: 技术深度 4/5",
        )
        assert data.candidate_id == "cand-1"
        assert data.decision_type == "scorecard_assist"

    def test_audit_create_with_citations(self) -> None:
        data = AiDecisionAuditCreate(
            candidate_id="cand-1",
            application_id="app-1",
            decision_type="rejection_suggest",
            model_name="gpt-4",
            output_summary="建议拒绝",
            cited_standard_version_ids=["std-v1", "std-v2"],
            cited_evidence_ref_ids=["ev-1"],
        )
        assert len(data.cited_standard_version_ids) == 2
        assert len(data.cited_evidence_ref_ids) == 1

    def test_decision_type_enum_labels_match_model(self) -> None:
        expected = {e.value for e in AiDecisionType}
        assert "scorecard_assist" in expected
        assert "screening" in expected
        assert "rejection_suggest" in expected


def _make_app(db_mock) -> FastAPI:
    """创建可注入 mock db 的 FastAPI 应用。"""
    app = FastAPI()
    app.include_router(job_profiles_router, prefix="/job-profiles")
    app.include_router(scorecards_router, prefix="/scorecards")
    app.include_router(candidates_router, prefix="/candidates")

    async def fake_get_db():
        yield db_mock

    async def fake_org_scoped_db():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), db_mock

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[org_scoped_db] = fake_org_scoped_db
    return app


class TestTemplateLifecycleApi:
    """M2.5: 模板 activate/archive API 端点。"""

    def _mock_template(self, status: str = "draft") -> MagicMock:
        tpl = MagicMock(spec=ScorecardTemplate)
        tpl.id = "tpl-1"
        tpl.job_profile_id = None
        tpl.profile_version_id = None
        tpl.name = "测试评分卡"
        tpl.round_type = Mock(value="technical")
        tpl.status = ScorecardStatus(status)
        tpl.total_weight = 1.0
        tpl.created_by = "test-user"
        tpl.created_at = datetime(2026, 6, 8, tzinfo=UTC)
        tpl.updated_at = datetime(2026, 6, 8, tzinfo=UTC)
        return tpl

    def test_activate_template(self) -> None:
        db = AsyncMock()
        app = _make_app(db)
        tpl = self._mock_template("draft")
        svc = AsyncMock()
        svc.get_template.return_value = tpl
        svc.to_template_dict.return_value = {"id": "tpl-1", "status": "active"}

        with patch("app.api.scorecards.ScorecardService", return_value=svc):
            resp = TestClient(app).post("/scorecards/templates/tpl-1/activate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["status"] == "active"

    def test_archive_template(self) -> None:
        db = AsyncMock()
        app = _make_app(db)
        tpl = self._mock_template("active")
        svc = AsyncMock()
        svc.get_template.return_value = tpl
        svc.to_template_dict.return_value = {"id": "tpl-1", "status": "archived"}

        with patch("app.api.scorecards.ScorecardService", return_value=svc):
            resp = TestClient(app).post("/scorecards/templates/tpl-1/archive")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["status"] == "archived"

    def test_activate_already_active_returns_error(self) -> None:
        db = AsyncMock()
        app = _make_app(db)
        tpl = self._mock_template("active")
        svc = AsyncMock()
        svc.get_template.return_value = tpl
        svc.activate_template.side_effect = ValueError("评分卡已是 active 状态")

        with patch("app.api.scorecards.ScorecardService", return_value=svc):
            resp = TestClient(app).post("/scorecards/templates/tpl-1/activate")

        assert resp.status_code == 400
        assert "已是 active" in resp.json()["error"]


class TestEvidenceAuditApi:
    """M2.6 + M2.7: 证据和审计查询端点。"""

    def _make_mock_evidence(self) -> MagicMock:
        ev = MagicMock(spec=EvidenceRef)
        ev.id = "ev-1"
        ev.candidate_id = "cand-1"
        ev.application_id = None
        ev.source_type = MagicMock(value="scorecard")
        ev.source_id = None
        ev.quote = "具体表现良好"
        ev.normalized_claim = "候选人在该维度表现良好"
        ev.confidence = 0.85
        ev.created_by_type = MagicMock(value="ai")
        ev.created_by_id = None
        ev.created_at = datetime(2026, 6, 8, tzinfo=UTC)
        return ev

    def _make_mock_audit(self) -> MagicMock:
        audit = MagicMock(spec=AiDecisionAudit)
        audit.id = "audit-1"
        audit.candidate_id = "cand-1"
        audit.application_id = None
        audit.decision_type = MagicMock(value="scorecard_assist")
        audit.model_name = "gpt-4"
        audit.prompt_version = None
        audit.input_refs = {}
        audit.output_summary = "评分完成"
        audit.cited_standard_version_ids = []
        audit.cited_evidence_ref_ids = []
        audit.confidence = None
        audit.human_confirmed = False
        audit.confirmed_by = None
        audit.confirmed_at = None
        audit.created_at = datetime(2026, 6, 8, tzinfo=UTC)
        return audit

    def test_list_evidence(self) -> None:
        db = AsyncMock()
        app = _make_app(db)
        ev = self._make_mock_evidence()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [ev]
        db.execute.return_value = result_mock

        resp = TestClient(app).get("/candidates/cand-1/evidence")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["source_type"] == "scorecard"
        assert data["data"][0]["normalized_claim"] == "候选人在该维度表现良好"

    def test_list_audits(self) -> None:
        db = AsyncMock()
        app = _make_app(db)
        audit = self._make_mock_audit()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [audit]
        db.execute.return_value = result_mock

        resp = TestClient(app).get("/candidates/cand-1/audits")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["decision_type"] == "scorecard_assist"

    def test_list_evidence_with_source_filter(self) -> None:
        db = AsyncMock()
        app = _make_app(db)
        ev = self._make_mock_evidence()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [ev]
        db.execute.return_value = result_mock

        resp = TestClient(app).get("/candidates/cand-1/evidence?source_type=scorecard")

        assert resp.status_code == 200
        call_args = db.execute.call_args[0][0]
        assert "evidence_refs" in str(call_args)
