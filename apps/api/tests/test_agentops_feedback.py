"""Tests for AgentOps Feedback module (P2-C Stage 11).

Covers:
- FeedbackCategory / FeedbackSource enum values
- FeedbackCreate / FeedbackTarget schema validation
- FeedbackStore create, query, filter, stats aggregation
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agentops.feedback import (
    AgentFeedbackModel,
    FeedbackCategory,
    FeedbackCreate,
    FeedbackResponse,
    FeedbackSource,
    FeedbackStats,
    FeedbackTarget,
)
from app.agentops.feedback.models import FeedbackStore
from app.agentops.feedback.service import FeedbackService
from app.core.database import AsyncSessionLocal, engine


# ════════════════════════════════════════════════════════════
# Schema validation
# ════════════════════════════════════════════════════════════


class TestFeedbackCategory:
    def test_all_values_are_unique(self) -> None:
        values = [c.value for c in FeedbackCategory]
        assert len(values) == len(set(values))

    def test_known_categories(self) -> None:
        assert FeedbackCategory.RELEVANCE == "relevance"
        assert FeedbackCategory.ACCURACY == "accuracy"
        assert FeedbackCategory.COMPLETENESS == "completeness"
        assert FeedbackCategory.TONE == "tone"
        assert FeedbackCategory.TOOL_CORRECTNESS == "tool_call"
        assert FeedbackCategory.QUALITY == "quality"
        assert FeedbackCategory.CUSTOM == "custom"


class TestFeedbackSource:
    def test_all_values_are_unique(self) -> None:
        values = [s.value for s in FeedbackSource]
        assert len(values) == len(set(values))

    def test_known_sources(self) -> None:
        assert FeedbackSource.END_USER == "end_user"
        assert FeedbackSource.ANNOTATOR == "annotator"
        assert FeedbackSource.AUTO_RULE == "auto_rule"
        assert FeedbackSource.AUTO_EVALUATOR == "auto_eval"


class TestFeedbackCreate:
    def test_minimal_valid(self) -> None:
        req = FeedbackCreate(category=FeedbackCategory.QUALITY, score=0.85)
        assert req.category == FeedbackCategory.QUALITY
        assert req.score == 0.85
        assert req.reason is None
        assert req.source == FeedbackSource.END_USER
        assert req.target.trace_id is None

    def test_full_valid(self) -> None:
        req = FeedbackCreate(
            category=FeedbackCategory.ACCURACY,
            score=0.3,
            reason="答案不准确，JD 要求 5 年经验但说 3 年即可",
            target=FeedbackTarget(trace_id="trace-123", span_id="span-456", message_id="msg-789"),
            source=FeedbackSource.ANNOTATOR,
            tags=["bad_case", "jd_quality"],
        )
        assert req.score == 0.3
        assert req.target.trace_id == "trace-123"

    def test_score_clamping(self) -> None:
        with pytest.raises(ValueError):
            FeedbackCreate(category=FeedbackCategory.QUALITY, score=1.5)

    def test_score_negative(self) -> None:
        with pytest.raises(ValueError):
            FeedbackCreate(category=FeedbackCategory.QUALITY, score=-0.1)

    def test_reason_empty_string_normalized(self) -> None:
        req = FeedbackCreate(category=FeedbackCategory.QUALITY, score=0.5, reason="  ")
        assert req.reason is None

    def test_reason_too_long(self) -> None:
        with pytest.raises(ValueError):
            FeedbackCreate(category=FeedbackCategory.QUALITY, score=0.5, reason="x" * 2001)

    def test_tags_max_length(self) -> None:
        with pytest.raises(ValueError):
            FeedbackCreate(category=FeedbackCategory.QUALITY, score=0.5, tags=["t"] * 11)


# ════════════════════════════════════════════════════════════
# DB integration tests
# ════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(loop_scope="module")
async def clean_table():
    """Clean agent_feedback table before each test.

    Disposes the engine first in case another test's ``client`` fixture
    called ``engine.dispose()`` — SQLAlchemy will create a fresh pool
    on next ``AsyncSessionLocal()`` usage.
    """
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(AgentFeedbackModel.__table__.delete())
        await db.commit()


@pytest_asyncio.fixture(loop_scope="module")
async def store() -> FeedbackStore:
    return FeedbackStore()


@pytest.mark.asyncio(loop_scope="module")
class TestFeedbackStore:
    """FeedbackStore direct integration tests."""

    async def test_save_and_get(self, store: FeedbackStore, clean_table: None) -> None:
        fid = str(uuid4())
        m = AgentFeedbackModel(
            id=fid,
            category="accuracy",
            source="end_user",
            score=0.75,
            reason="不错",
            trace_id="t1",
        )
        saved = await store.save(m)
        assert saved is not None
        assert saved.id == fid

        got = await store.get(fid)
        assert got is not None
        assert got.category == "accuracy"
        assert got.score == 0.75
        assert got.trace_id == "t1"

    async def test_get_not_found(self, store: FeedbackStore, clean_table: None) -> None:
        got = await store.get("nonexistent")
        assert got is None

    async def test_list_filters(self, store: FeedbackStore, clean_table: None) -> None:
        """Test category filter on list."""
        async with AsyncSessionLocal() as db:
            for i, cat in enumerate(["accuracy", "relevance", "accuracy"]):
                db.add(AgentFeedbackModel(
                    id=str(uuid4()),
                    category=cat,
                    source="end_user",
                    score=0.5 + i * 0.2,
                ))
            await db.commit()

        items, total = await store.list(category="accuracy")
        assert total == 2
        assert len(items) == 2
        for item in items:
            assert item.category == "accuracy"

    async def test_list_pagination(self, store: FeedbackStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            for i in range(5):
                db.add(AgentFeedbackModel(
                    id=str(uuid4()),
                    category="quality",
                    source="end_user",
                    score=0.5 + i * 0.1,
                ))
            await db.commit()

        items, total = await store.list(limit=2, offset=0)
        assert total == 5
        assert len(items) == 2

        items2, _ = await store.list(limit=2, offset=2)
        assert len(items2) == 2

    async def test_list_multi_filter(self, store: FeedbackStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            db.add(AgentFeedbackModel(
                id=str(uuid4()), category="accuracy", source="end_user",
                score=0.9, trace_id="t1",
            ))
            db.add(AgentFeedbackModel(
                id=str(uuid4()), category="relevance", source="end_user",
                score=0.8, trace_id="t2",
            ))
            await db.commit()

        items, total = await store.list(category="accuracy", trace_id="t1")
        assert total == 1
        assert items[0].score == 0.9

        items2, total2 = await store.list(category="accuracy", trace_id="t2")
        assert total2 == 0


@pytest.mark.asyncio(loop_scope="module")
class TestFeedbackStats:
    """FeedbackStore stats aggregation tests."""

    async def test_empty_stats(self, store: FeedbackStore, clean_table: None) -> None:
        stats = await store.stats()
        assert stats.total_count == 0
        assert stats.overall_avg_score == 0.0
        assert stats.category_stats == {}

    async def test_stats_single_category(self, store: FeedbackStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            for score in [0.5, 0.7, 0.9]:
                db.add(AgentFeedbackModel(
                    id=str(uuid4()), category="accuracy", source="end_user", score=score,
                ))
            await db.commit()

        stats = await store.stats()
        assert stats.total_count == 3
        assert stats.overall_avg_score == pytest.approx(0.7, rel=0.01)
        assert "accuracy" in stats.category_stats
        assert stats.category_stats["accuracy"]["count"] == 3
        assert stats.category_stats["accuracy"]["avg_score"] == pytest.approx(0.7, rel=0.01)

    async def test_stats_multi_category(self, store: FeedbackStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            db.add(AgentFeedbackModel(id=str(uuid4()), category="accuracy", source="end_user", score=1.0))
            db.add(AgentFeedbackModel(id=str(uuid4()), category="accuracy", source="end_user", score=0.0))
            db.add(AgentFeedbackModel(id=str(uuid4()), category="relevance", source="end_user", score=0.8))
            await db.commit()

        stats = await store.stats()
        assert stats.total_count == 3
        assert stats.category_stats["accuracy"]["count"] == 2
        assert stats.category_stats["accuracy"]["avg_score"] == pytest.approx(0.5, rel=0.01)
        assert stats.category_stats["relevance"]["count"] == 1
        assert stats.category_stats["relevance"]["avg_score"] == 0.8

    async def test_stats_with_trace_filter(self, store: FeedbackStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            for i in range(3):
                db.add(AgentFeedbackModel(
                    id=str(uuid4()), category="accuracy", source="end_user",
                    score=0.5, trace_id="t1",
                ))
            db.add(AgentFeedbackModel(
                id=str(uuid4()), category="accuracy", source="end_user",
                score=1.0, trace_id="t2",
            ))
            await db.commit()

        stats = await store.stats(trace_id="t1")
        assert stats.total_count == 3
        assert stats.overall_avg_score == 0.5

        stats2 = await store.stats(trace_id="t2")
        assert stats2.total_count == 1
        assert stats2.overall_avg_score == 1.0


@pytest.mark.asyncio(loop_scope="module")
class TestFeedbackService:
    """FeedbackService integration tests."""

    async def test_create_feedback_basic(self, clean_table: None) -> None:
        service = FeedbackService()
        req = FeedbackCreate(
            category=FeedbackCategory.QUALITY,
            score=0.9,
            reason="很不错",
            target=FeedbackTarget(trace_id="t1", session_id="s1"),
            tags=["good"],
        )
        model = await service.create_feedback(req, user_id="user-1")
        assert model is not None
        assert model.category == "quality"
        assert model.score == 0.9
        assert model.trace_id == "t1"
        assert model.session_id == "s1"
        assert model.user_id == "user-1"

    async def test_create_feedback_minimal(self, clean_table: None) -> None:
        service = FeedbackService()
        req = FeedbackCreate(category=FeedbackCategory.RELEVANCE, score=0.4)
        model = await service.create_feedback(req)
        assert model is not None
        assert model.category == "relevance"
        assert model.score == 0.4

    async def test_create_feedback_negative_score(self, clean_table: None) -> None:
        """Low score is valid — it means bad feedback."""
        service = FeedbackService()
        req = FeedbackCreate(category=FeedbackCategory.ACCURACY, score=0.0)
        model = await service.create_feedback(req, user_id="user-1")
        assert model is not None
        assert model.score == 0.0

    async def test_list_and_count(self, clean_table: None) -> None:
        service = FeedbackService()
        async with AsyncSessionLocal() as db:
            for i in range(3):
                await service.create_feedback(
                    FeedbackCreate(category=FeedbackCategory.QUALITY, score=0.5 + i * 0.1),
                    user_id="user-1",
                )

        items, total = await service.list_feedback(user_id="user-1")
        assert total == 3
        assert len(items) == 3

    async def test_get_stats(self, clean_table: None) -> None:
        service = FeedbackService()
        async with AsyncSessionLocal() as db:
            for score in [0.5, 0.7, 0.9]:
                await service.create_feedback(
                    FeedbackCreate(category=FeedbackCategory.ACCURACY, score=score),
                    user_id="user-1",
                )

        stats = await service.get_stats(user_id="user-1")
        assert isinstance(stats, FeedbackStats)
        assert stats.total_count == 3
        assert stats.overall_avg_score == pytest.approx(0.7, rel=0.01)

    async def test_create_with_annotator_source(self, clean_table: None) -> None:
        """Annotator source feedback should still persist correctly."""
        service = FeedbackService()
        req = FeedbackCreate(
            category=FeedbackCategory.COMPLETENESS,
            score=0.2,
            reason="缺少关键信息",
            source=FeedbackSource.ANNOTATOR,
            tags=["bad_case"],
        )
        model = await service.create_feedback(req, user_id="annotator-1")
        assert model is not None
        assert model.source == "annotator"
        assert model.category == "completeness"
