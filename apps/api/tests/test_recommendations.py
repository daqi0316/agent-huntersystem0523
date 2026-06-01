"""Recommendations API + service tests."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.main import app
from app.models.recommendation import Recommendation, RecommendationType
from app.services.recommendation_service import RecommendationService


# ── Fixtures ───────────────────────────────────────────

@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
def override_get_db(mock_db_session):
    async def _mock_get_db():
        yield mock_db_session
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def override_auth():
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


def make_rec(
    rec_id: str = "rec-1", user_id: str = "user-1", read: bool = False,
    dismissed: bool = False, score: int = 85, rtype: str = "candidate_job_match",
):
    r = Mock(spec=Recommendation)
    r.id = rec_id
    r.user_id = user_id
    r.type = RecommendationType(rtype)
    r.title = "候选人匹配: 后端工程师"
    r.description = "为职位推荐了一名候选人"
    r.candidate_id = "cand-1"
    r.job_id = "job-1"
    r.score = score
    r.reason = "匹配技能: python, fastapi；3年经验"
    r.read = read
    r.dismissed = dismissed
    r.created_at = None
    return r


# ── Service Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recommendations_empty():
    """空推荐列表返回空数组。"""
    db = AsyncMock()
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    svc = RecommendationService(db)
    recs = await svc.list_recommendations("user-1")

    assert recs == []


@pytest.mark.asyncio
async def test_list_recommendations_with_data():
    """有推荐时正确返回列表。"""
    db = AsyncMock()
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = [
        make_rec("rec-1"),
        make_rec("rec-2"),
    ]
    db.execute.return_value = mock_result

    svc = RecommendationService(db)
    recs = await svc.list_recommendations("user-1")

    assert len(recs) == 2
    assert recs[0].id == "rec-1"
    assert recs[1].id == "rec-2"


@pytest.mark.asyncio
async def test_count_unread():
    """未读计数正确。"""
    db = AsyncMock()
    mock_result = Mock()
    mock_result.scalar.return_value = 3
    db.execute.return_value = mock_result

    svc = RecommendationService(db)
    count = await svc.count_unread("user-1")

    assert count == 3


@pytest.mark.asyncio
async def test_mark_read_success():
    """标记已读成功返回 True。"""
    db = AsyncMock()
    rec = make_rec(read=False)
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = rec
    db.execute.return_value = mock_result

    svc = RecommendationService(db)
    ok = await svc.mark_read("rec-1", "user-1")

    assert ok is True
    assert rec.read is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_read_not_found():
    """标记不存在的推荐返回 False。"""
    db = AsyncMock()
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    svc = RecommendationService(db)
    ok = await svc.mark_read("nonexistent", "user-1")

    assert ok is False


@pytest.mark.asyncio
async def test_dismiss_success():
    """忽略推荐成功返回 True。"""
    db = AsyncMock()
    rec = make_rec(dismissed=False)
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = rec
    db.execute.return_value = mock_result

    svc = RecommendationService(db)
    ok = await svc.dismiss("rec-1", "user-1")

    assert ok is True
    assert rec.dismissed is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_all_read():
    """全部标记已读返回更新数。"""
    db = AsyncMock()
    mock_result = Mock()
    mock_result.rowcount = 5
    db.execute.return_value = mock_result

    svc = RecommendationService(db)
    count = await svc.mark_all_read("user-1")

    assert count == 5
    db.commit.assert_awaited_once()


# ── Matching Engine Tests ──────────────────────────────


@pytest.mark.asyncio
async def test_compute_match_full():
    """技能全匹配 + 经验达标 = 高分。"""
    db = AsyncMock()
    svc = RecommendationService(db)

    job = Mock()
    job.requirements = "需要 Python、FastAPI、PostgreSQL 技能，3年以上经验"
    job.title = "后端工程师"

    candidate = Mock()
    candidate.skills = ["Python", "FastAPI", "PostgreSQL", "Docker"]
    candidate.experience_years = 5
    candidate.current_company = "Tech Co"
    candidate.current_title = "高级后端工程师"

    score, reason = await svc._compute_match(job, candidate)
    assert score >= 70
    assert "python" in reason or "Python" in reason
    assert "fastapi" in reason


@pytest.mark.asyncio
async def test_compute_match_low():
    """完全不匹配 = 低分。"""
    db = AsyncMock()
    svc = RecommendationService(db)

    job = Mock()
    job.requirements = "需要 Python、React、AWS 经验"
    job.title = "全栈工程师"

    candidate = Mock()
    candidate.skills = ["厨师", "驾驶", "会计"]
    candidate.experience_years = 0
    candidate.current_company = ""
    candidate.current_title = ""

    score, reason = await svc._compute_match(job, candidate)
    assert score < 50


@pytest.mark.asyncio
async def test_extract_keywords():
    """关键词提取正确。"""
    text = "需要 Python 和 FastAPI 经验，熟悉 Docker、Kubernetes，掌握 Machine Learning"
    keywords = RecommendationService._extract_keywords(text)

    assert "python" in keywords
    assert "fastapi" in keywords
    assert "docker" in keywords
    assert "machine learning" in keywords


@pytest.mark.asyncio
async def test_extract_experience_requirement():
    """经验年数提取正确。"""
    assert RecommendationService._extract_experience_requirement("3年以上经验") == 3
    assert RecommendationService._extract_experience_requirement("5年以上") == 5
    assert RecommendationService._extract_experience_requirement("2-3年") == 2
    assert RecommendationService._extract_experience_requirement("至少 3 年") == 3
    assert RecommendationService._extract_experience_requirement("无明确要求") is None


# ── API Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recommendations_api_empty(client, override_get_db, override_auth, mock_db_session):
    """API 返回空列表。"""
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    resp = await client.get("/api/v1/recommendations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_unread_count_api(client, override_get_db, override_auth, mock_db_session):
    """API 返回未读计数。"""
    mock_result = Mock()
    mock_result.scalar.return_value = 2
    mock_db_session.execute.return_value = mock_result

    resp = await client.get("/api/v1/recommendations/unread-count")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_mark_read_api(client, override_get_db, override_auth, mock_db_session):
    """API 标记已读成功。"""
    rec = make_rec(read=False)
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = rec
    mock_db_session.execute.return_value = mock_result

    resp = await client.post("/api/v1/recommendations/rec-1/read")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_dismiss_api(client, override_get_db, override_auth, mock_db_session):
    """API 忽略推荐成功。"""
    rec = make_rec(dismissed=False)
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = rec
    mock_db_session.execute.return_value = mock_result

    resp = await client.post("/api/v1/recommendations/rec-1/dismiss")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_mark_read_all_api(client, override_get_db, override_auth, mock_db_session):
    """API 全部标记已读成功。"""
    mock_result = Mock()
    mock_result.rowcount = 3
    mock_db_session.execute.return_value = mock_result

    resp = await client.post("/api/v1/recommendations/read-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["updated_count"] == 3


@pytest.mark.asyncio
async def test_trigger_api(client, override_get_db, override_auth, mock_db_session):
    """API 手动触发推荐扫描成功。"""
    with patch(
        "app.services.recommendation_service.RecommendationService.generate_recommendations",
        new_callable=AsyncMock,
        return_value=[make_rec("rec-1")],
    ):
        resp = await client.post("/api/v1/recommendations/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
