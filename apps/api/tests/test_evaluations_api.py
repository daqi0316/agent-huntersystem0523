"""Evaluations API tests — mock DB via app.dependency_overrides."""

from unittest.mock import AsyncMock, Mock

import pytest

from app.api.evaluations import _build_dimension_scores, _clamp
from app.models.application import Application, ApplicationStatus
from app.models.candidate import Candidate



@pytest.fixture
def mock_db_session():
    """Create a bare mock DB session — each test configures .execute()."""
    return AsyncMock()


@pytest.fixture
def override_get_db(mock_db_session):
    """Override get_db dependency at the FastAPI app level."""
    from app.core.database import get_db
    from app.main import app

    async def _mock_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


def _make_mock_candidate(
    candidate_id: str = "cand-001",
    name: str = "张三",
    skills: list[str] | None = None,
) -> Mock:
    c = Mock(spec=Candidate)
    c.id = candidate_id
    c.name = name
    c.skills = skills or ["Python", "FastAPI"]
    return c


def _make_mock_job(title: str = "后端工程师") -> Mock:
    j = Mock()
    j.title = title
    return j


def _make_mock_application(
    candidate_id: str = "cand-001",
    job_id: str = "job-001",
    match_score: float = 85.0,
    status: ApplicationStatus = ApplicationStatus.SCREENING,
    ai_summary: str = "优秀候选人",
) -> Mock:
    app = Mock(spec=Application)
    app.candidate_id = candidate_id
    app.job_id = job_id
    app.match_score = match_score
    app.status = status
    app.ai_summary = ai_summary
    app.candidate = _make_mock_candidate(candidate_id=candidate_id)
    app.job = _make_mock_job()
    app.created_at = Mock()
    app.created_at.isoformat = Mock(return_value="2026-05-24T00:00:00")
    app.updated_at = Mock()
    app.updated_at.isoformat = Mock(return_value="2026-05-24T00:00:00")
    return app


def _configure_list_db(mock_db, applications, total=None):
    """Configure mock_db.execute to return list/query-result mocks."""
    mock_result = Mock()
    # scalar(), scalars() are all synchronous SQLAlchemy result methods
    mock_result.scalar = Mock(return_value=total if total is not None else len(applications))
    scalars_mock = Mock()
    scalars_mock.all = Mock(return_value=applications)
    mock_result.scalars = Mock(return_value=scalars_mock)

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_db.execute = mock_execute
    return mock_db, mock_result


# ── List endpoint tests ──────────────────────────────────────────────────


async def test_list_evaluations_basic(client, override_get_db, mock_db_session):
    """List evaluations returns paginated results."""
    apps = [_make_mock_application(), _make_mock_application(candidate_id="cand-002")]
    _configure_list_db(mock_db_session, apps)

    resp = await client.get("/api/v1/evaluations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["items"]) == 2
    assert body["total"] == 2


async def test_list_evaluations_with_search(client, override_get_db, mock_db_session):
    """List evaluations supports search filter."""
    app = _make_mock_application(ai_summary="优秀Python开发者")
    _configure_list_db(mock_db_session, [app])

    resp = await client.get("/api/v1/evaluations?search=Python")
    assert resp.status_code == 200


async def test_list_evaluations_with_status_filter(client, override_get_db, mock_db_session):
    """List evaluations supports status filter."""
    app = _make_mock_application(status=ApplicationStatus.INTERVIEW)
    _configure_list_db(mock_db_session, [app])

    resp = await client.get("/api/v1/evaluations?status=interview")
    assert resp.status_code == 200


async def test_list_evaluations_invalid_status_ignored(client, override_get_db, mock_db_session):
    """Invalid status value is silently ignored (pass)."""
    _configure_list_db(mock_db_session, [], total=0)
    resp = await client.get("/api/v1/evaluations?status=invalid_status_xyz")
    assert resp.status_code == 200


async def test_list_evaluations_with_candidate_id(client, override_get_db, mock_db_session):
    """List evaluations supports candidate_id filter."""
    app = _make_mock_application(candidate_id="cand-099")
    _configure_list_db(mock_db_session, [app])

    resp = await client.get("/api/v1/evaluations?candidate_id=cand-099")
    assert resp.status_code == 200


async def test_list_evaluations_pagination(client, override_get_db, mock_db_session):
    """List evaluations respects skip and limit params."""
    _configure_list_db(mock_db_session, [], total=50)

    resp = await client.get("/api/v1/evaluations?skip=10&limit=5")
    assert resp.status_code == 200


async def test_list_evaluations_empty(client, override_get_db, mock_db_session):
    """List evaluations returns empty list when no records."""
    _configure_list_db(mock_db_session, [], total=0)

    resp = await client.get("/api/v1/evaluations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


# ── Get single evaluation tests ──────────────────────────────────────────


async def test_get_evaluation_found(client, override_get_db, mock_db_session):
    """Get single evaluation returns data for existing candidate."""
    app = _make_mock_application(match_score=92.0)
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = Mock(return_value=app)

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_db_session.execute = mock_execute

    resp = await client.get("/api/v1/evaluations/cand-001")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["overall_score"] == 92.0
    assert data["name"] == "张三"


async def test_get_evaluation_not_found(client, override_get_db, mock_db_session):
    """Get single evaluation returns 404 for non-existent candidate."""
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = Mock(return_value=None)

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_db_session.execute = mock_execute

    resp = await client.get("/api/v1/evaluations/nonexistent")
    assert resp.status_code == 404


# ── Pure function tests ──────────────────────────────────────────────────


class TestBuildDimensionScores:
    def test_with_valid_score(self):
        scores = _build_dimension_scores(85.0)
        assert len(scores) == 5
        assert scores[0]["name"] == "专业技能"
        assert scores[0]["score"] == 85.0
        assert scores[1]["name"] == "工作经验"
        assert scores[2]["name"] == "教育背景"
        assert scores[3]["name"] == "沟通能力"
        assert scores[4]["name"] == "团队协作"

    def test_with_none_score(self):
        scores = _build_dimension_scores(None)
        assert len(scores) == 5
        assert all(s["score"] == 0 for s in scores)


class TestClamp:
    def test_clamp_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_clamp_below_min(self):
        assert _clamp(-10.0) == 0.0

    def test_clamp_above_max(self):
        assert _clamp(150.0) == 100.0

    def test_clamp_rounds_to_one_decimal(self):
        assert _clamp(55.555) == 55.6
