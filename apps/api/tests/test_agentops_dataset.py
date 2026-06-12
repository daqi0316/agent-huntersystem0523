"""Tests for AgentOps Dataset module (P2-C Stage 12).

Covers:
- DatasetItemCategory / DatasetItemSource enum values
- DatasetItemCreate schema validation
- DatasetStore create, query, filter, stats, delete
- DatasetService create, list, delete, stats
- DatasetService.create_from_feedback integration
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from app.agentops.dataset import (
    DatasetItemCategory,
    DatasetItemCreate,
    DatasetItemResponse,
    DatasetItemSource,
    DatasetService,
    DatasetStats,
    DatasetStore,
)
from app.agentops.dataset.models import ExperimentDatasetItemModel
from app.agentops.feedback.schemas import FeedbackCategory, FeedbackCreate, FeedbackSource
from app.core.database import AsyncSessionLocal, engine


# ════════════════════════════════════════════════════════════
# Schema validation
# ════════════════════════════════════════════════════════════


class TestDatasetItemCategory:
    def test_all_values_are_unique(self) -> None:
        values = [c.value for c in DatasetItemCategory]
        assert len(values) == len(set(values))

    def test_known_categories(self) -> None:
        assert DatasetItemCategory.RESUME_PARSE == "resume_parse"
        assert DatasetItemCategory.SCREENING == "screening"
        assert DatasetItemCategory.JD_GENERATION == "jd_generation"
        assert DatasetItemCategory.INTERVIEW_SCHEDULING == "interview_scheduling"
        assert DatasetItemCategory.CONVERSATION == "conversation"
        assert DatasetItemCategory.TOOL_CALL == "tool_call"
        assert DatasetItemCategory.OTHER == "other"


class TestDatasetItemSource:
    def test_all_values_are_unique(self) -> None:
        values = [s.value for s in DatasetItemSource]
        assert len(values) == len(set(values))

    def test_known_sources(self) -> None:
        assert DatasetItemSource.BAD_CASE == "bad_case"
        assert DatasetItemSource.SYSTEM_FAILURE == "system_failure"
        assert DatasetItemSource.ANNOTATION == "annotation"
        assert DatasetItemSource.MANUAL == "manual"
        assert DatasetItemSource.SAMPLED == "sampled"


class TestDatasetItemCreate:
    def test_default_values(self) -> None:
        req = DatasetItemCreate()
        assert req.category == DatasetItemCategory.OTHER
        assert req.source == DatasetItemSource.MANUAL
        assert req.tags == []
        assert req.priority == 0
        assert req.score == 0.0

    def test_tags_max_length(self) -> None:
        with pytest.raises(ValueError):
            DatasetItemCreate(tags=["t"] * 21)

    def test_priority_range(self) -> None:
        with pytest.raises(ValueError):
            DatasetItemCreate(priority=6)
        with pytest.raises(ValueError):
            DatasetItemCreate(priority=-1)

    def test_score_range(self) -> None:
        with pytest.raises(ValueError):
            DatasetItemCreate(score=1.5)
        with pytest.raises(ValueError):
            DatasetItemCreate(score=-0.1)

    def test_full_construction(self) -> None:
        req = DatasetItemCreate(
            category=DatasetItemCategory.SCREENING,
            source=DatasetItemSource.BAD_CASE,
            trace_id="trace-1",
            entity_type="candidate",
            entity_id="cand-1",
            input_snapshot={"resume": "..."},
            expected_output={"decision": "advance"},
            actual_output={"decision": "reject"},
            tags=["urgent", "regression"],
            is_bad_case=True,
            priority=3,
            score=0.8,
            description="Bad case from user feedback",
        )
        assert req.category == DatasetItemCategory.SCREENING
        assert req.source == DatasetItemSource.BAD_CASE
        assert req.priority == 3
        assert req.score == 0.8
        assert len(req.tags) == 2


# ════════════════════════════════════════════════════════════
# DB integration tests
# ════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(loop_scope="module")
async def clean_table():
    """Clean agent_dataset_item table before each test."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(ExperimentDatasetItemModel.__table__.delete())
        await db.commit()


@pytest_asyncio.fixture(loop_scope="module")
async def store() -> DatasetStore:
    return DatasetStore()


@pytest.mark.asyncio(loop_scope="module")
class TestDatasetStore:
    """DatasetStore direct integration tests."""

    async def test_save_and_get(self, store: DatasetStore, clean_table: None) -> None:
        did = str(uuid4())
        m = ExperimentDatasetItemModel(
            id=did,
            category="screening",
            source="bad_case",
            input_snapshot={"resume": "..."},
            expected_output={"decision": "advance"},
            actual_output={"decision": "reject"},
            is_bad_case=True,
            score=0.75,
        )
        saved = await store.save(m)
        assert saved is not None
        assert saved.id == did

        got = await store.get(did)
        assert got is not None
        assert got.category == "screening"
        assert got.is_bad_case is True
        assert got.score == 0.75

    async def test_get_not_found(self, store: DatasetStore, clean_table: None) -> None:
        got = await store.get("nonexistent")
        assert got is None

    async def test_list_filters(self, store: DatasetStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            for i, cat in enumerate(["screening", "resume_parse", "screening"]):
                db.add(ExperimentDatasetItemModel(
                    id=str(uuid4()),
                    category=cat,
                    source="manual",
                    score=0.5 + i * 0.2,
                ))
            await db.commit()

        items, total = await store.list(category="screening")
        assert total == 2
        assert len(items) == 2
        for item in items:
            assert item.category == "screening"

    async def test_list_pagination(self, store: DatasetStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            for i in range(5):
                db.add(ExperimentDatasetItemModel(
                    id=str(uuid4()),
                    category="conversation",
                    source="manual",
                    score=0.5 + i * 0.1,
                ))
            await db.commit()

        items, total = await store.list(limit=2, offset=0)
        assert total == 5
        assert len(items) == 2

        items2, _ = await store.list(limit=2, offset=2)
        assert len(items2) == 2

    async def test_list_bad_case_filter(self, store: DatasetStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            db.add(ExperimentDatasetItemModel(
                id=str(uuid4()), category="screening", source="manual",
                is_bad_case=True, score=0.2,
            ))
            db.add(ExperimentDatasetItemModel(
                id=str(uuid4()), category="screening", source="manual",
                is_bad_case=False, score=0.9,
            ))
            await db.commit()

        items, total = await store.list(is_bad_case=True)
        assert total == 1
        assert items[0].score == 0.2

        items2, total2 = await store.list(is_bad_case=False)
        assert total2 == 1
        assert items2[0].score == 0.9

    async def test_delete(self, store: DatasetStore, clean_table: None) -> None:
        did = str(uuid4())
        m = ExperimentDatasetItemModel(id=did, category="jd_generation", source="manual")
        await store.save(m)

        deleted = await store.delete(did)
        assert deleted is True

        got = await store.get(did)
        assert got is None

        deleted_missing = await store.delete("nonexistent")
        assert deleted_missing is False

    async def test_stats_empty(self, store: DatasetStore, clean_table: None) -> None:
        stats = await store.stats()
        assert stats.total_count == 0
        assert stats.category_counts == {}
        assert stats.source_counts == {}
        assert stats.bad_case_count == 0

    async def test_stats_with_data(self, store: DatasetStore, clean_table: None) -> None:
        async with AsyncSessionLocal() as db:
            db.add(ExperimentDatasetItemModel(
                id=str(uuid4()), category="screening", source="bad_case",
                is_bad_case=True, score=0.3,
            ))
            db.add(ExperimentDatasetItemModel(
                id=str(uuid4()), category="screening", source="manual",
                is_bad_case=False, score=0.9,
            ))
            db.add(ExperimentDatasetItemModel(
                id=str(uuid4()), category="resume_parse", source="manual",
                is_bad_case=False, score=0.8,
            ))
            await db.commit()

        stats = await store.stats()
        assert stats.total_count == 3
        assert stats.category_counts["screening"] == 2
        assert stats.category_counts["resume_parse"] == 1
        assert stats.bad_case_count == 1


@pytest.mark.asyncio(loop_scope="module")
class TestDatasetService:
    """DatasetService integration tests."""

    async def test_create_and_get(self, clean_table: None) -> None:
        service = DatasetService()
        req = DatasetItemCreate(
            category=DatasetItemCategory.SCREENING,
            source=DatasetItemSource.BAD_CASE,
            trace_id="trace-1",
            input_snapshot={"resume": "..."},
            expected_output={"decision": "advance"},
            actual_output={"decision": "reject"},
            tags=["bad_case"],
            is_bad_case=True,
            score=0.3,
            description="User complained about rejection",
        )
        result = await service.create_item(req)
        assert result is not None
        assert result.category == "screening"
        assert result.source == "bad_case"
        assert result.is_bad_case is True
        assert result.score == 0.3
        assert result.trace_id == "trace-1"

        # verify get
        got = await service.get_item(result.id)
        assert got is not None
        assert got.id == result.id

    async def test_list_and_delete(self, clean_table: None) -> None:
        service = DatasetService()
        for i in range(3):
            await service.create_item(
                DatasetItemCreate(
                    category=DatasetItemCategory.CONVERSATION,
                    trace_id=f"trace-{i}",
                )
            )

        items, total = await service.list_items()
        assert total == 3
        assert len(items) == 3

        # delete one
        deleted = await service.delete_item(items[0].id)
        assert deleted is True

        items2, total2 = await service.list_items()
        assert total2 == 2

    async def test_get_stats(self, clean_table: None) -> None:
        service = DatasetService()
        for cat in [DatasetItemCategory.SCREENING, DatasetItemCategory.RESUME_PARSE]:
            await service.create_item(
                DatasetItemCreate(
                    category=cat,
                    source=DatasetItemSource.MANUAL,
                    is_bad_case=(cat == DatasetItemCategory.SCREENING),
                )
            )

        stats = await service.get_stats()
        assert isinstance(stats, DatasetStats)
        assert stats.total_count == 2

    async def test_get_item_not_found(self, clean_table: None) -> None:
        service = DatasetService()
        result = await service.get_item("nonexistent")
        assert result is None

    async def test_create_from_feedback_bad_case(self, clean_table: None) -> None:
        """Verify bad case feedback auto-creates a dataset item."""
        from app.agentops.feedback.models import AgentFeedbackModel, FeedbackStore

        fb_store = FeedbackStore()

        # 创建一条 annotator 反馈（自动 bad_case）
        fb = AgentFeedbackModel(
            id=str(uuid4()),
            category="accuracy",
            source="annotator",
            score=0.2,
            reason="Wrong screening decision",
            trace_id="trace-fb-1",
        )
        await fb_store.save(fb)

        # 从反馈生成 dataset item
        service = DatasetService()
        result = await service.create_from_feedback(fb.id)
        assert result is not None
        assert result.is_bad_case is True
        assert result.source == "bad_case"
        assert result.feedback_id == fb.id
        assert result.trace_id == "trace-fb-1"
        assert "bad_case" in result.tags

    async def test_create_from_feedback_non_bad_case(self, clean_table: None) -> None:
        """端用户反馈不应该自动标记 bad_case。"""
        from app.agentops.feedback.models import AgentFeedbackModel, FeedbackStore

        fb_store = FeedbackStore()
        fb = AgentFeedbackModel(
            id=str(uuid4()),
            category="quality",
            source="end_user",
            score=0.9,
            reason="Good job!",
            trace_id="trace-fb-2",
        )
        await fb_store.save(fb)

        service = DatasetService()
        result = await service.create_from_feedback(fb.id)
        assert result is not None
        assert result.is_bad_case is False
        assert "bad_case" not in result.tags

    async def test_create_from_feedback_not_found(self, clean_table: None) -> None:
        service = DatasetService()
        result = await service.create_from_feedback("nonexistent")
        assert result is None


@pytest.mark.asyncio(loop_scope="module")
class TestFeedbackDatasetExperimentIntegration:
    """闭环集成测试: feedback → dataset → experiment 全链路。"""

    async def test_full_cycle(self, clean_table: None) -> None:
        """创建一条差评反馈 → 转为 dataset item → 创建实验 → 执行 → 验证结果。"""
        from app.agentops.feedback.models import AgentFeedbackModel, FeedbackStore
        from app.agentops.dataset.experiment_service import ExperimentService
        from app.agentops.dataset.experiment_schemas import ExperimentCreate

        # Step 1: 创建一条 annotator 差评反馈
        fb_store = FeedbackStore()
        fb_id = str(uuid4())
        fb = AgentFeedbackModel(
            id=fb_id,
            category="accuracy",
            source="annotator",
            score=0.15,
            reason="Screening decision was wrong — rejected qualified candidate",
            trace_id="trace-full-cycle",
            target_entity_type="candidate",
            target_entity_id="cand-123",
        )
        await fb_store.save(fb)

        # Step 2: 差评 → Dataset item
        ds_service = DatasetService()
        ds_item = await ds_service.create_from_feedback(fb_id)
        assert ds_item is not None
        assert ds_item.is_bad_case is True
        assert ds_item.feedback_id == fb_id
        assert ds_item.trace_id == "trace-full-cycle"

        # 手动补充 expected_output/actual_output（service.create_from_feedback
        # 不会设置预期输出，这里补上以便实验能跑有效评估）
        from app.agentops.dataset.models import DatasetStore
        raw = await DatasetStore().get(ds_item.id)
        assert raw is not None
        raw.expected_output = {"decision": "advance", "reason": "qualified"}
        raw.actual_output = {"decision": "reject", "reason": "overqualified"}
        await DatasetStore().save(raw)

        # Step 3: 用 dataset item 创建实验
        exp_service = ExperimentService()
        exp = await exp_service.create_experiment(
            ExperimentCreate(
                name="Screening regression — full cycle",
                dataset_item_ids=[ds_item.id],
                evaluator_type="rule_based",
                tags=["regression", "full-cycle"],
            ),
            created_by="test-user",
        )
        assert exp is not None
        assert exp.status == "pending"
        assert ds_item.id in exp.dataset_item_ids

        # Step 4: 执行实验
        run = await exp_service.run_experiment(exp.id)
        assert run is not None
        assert run.status == "completed"
        assert run.total_items == 1

        # expected: {"decision": "advance", "reason": "qualified"}
        # actual:   {"decision": "reject", "reason": "overqualified"}
        # → 2 fields, 0 match = score 0.0, passed=False
        assert run.failed_items == 1
        assert run.passed_items == 0
        assert run.avg_score == 0.0

        # Step 5: 验证运行记录
        runs, total = await exp_service.list_runs(exp.id)
        assert total == 1
        assert runs[0].id == run.id

        run_detail = await exp_service.get_run(run.id)
        assert run_detail is not None
        assert run_detail.experiment_id == exp.id
        assert run_detail.total_items == 1
        assert run_detail.duration_ms > 0
