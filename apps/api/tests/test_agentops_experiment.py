"""Tests for AgentOps Experiment module (P2-C Stage 12).

Covers:
- Experiment schema validation
- ExperimentStore CRUD
- ExperimentService create/list/get
- Experiment run execution (rule_based evaluator)
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from app.agentops.dataset.experiment_models import ExperimentModel, ExperimentRunModel, ExperimentStore
from app.agentops.dataset.experiment_schemas import (
    ExperimentCreate,
    ExperimentRunCreate,
    ExperimentStatus,
)
from app.agentops.dataset.experiment_service import ExperimentService
from app.agentops.dataset.models import ExperimentDatasetItemModel
from app.core.database import AsyncSessionLocal, engine


# ════════════════════════════════════════════════════════════
# Schema validation
# ════════════════════════════════════════════════════════════


class TestExperimentStatus:
    def test_known_statuses(self) -> None:
        assert ExperimentStatus.PENDING == "pending"
        assert ExperimentStatus.RUNNING == "running"
        assert ExperimentStatus.COMPLETED == "completed"
        assert ExperimentStatus.FAILED == "failed"
        assert ExperimentStatus.CANCELLED == "cancelled"


class TestExperimentCreate:
    def test_default_values(self) -> None:
        req = ExperimentCreate(name="Test experiment")
        assert req.name == "Test experiment"
        assert req.description == ""
        assert req.dataset_item_ids == []
        assert req.evaluator_type == "rule_based"
        assert req.variants == []
        assert req.tags == []

    def test_variants_max_length(self) -> None:
        with pytest.raises(ValueError):
            ExperimentCreate(name="test", variants=[{}] * 11)

    def test_dataset_items_max_length(self) -> None:
        with pytest.raises(ValueError):
            ExperimentCreate(name="test", dataset_item_ids=["id"] * 1001)


# ════════════════════════════════════════════════════════════
# DB integration tests
# ════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(loop_scope="module")
async def clean_tables():
    """Clean experiment + dataset_item tables before each test."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(ExperimentRunModel.__table__.delete())
        await db.execute(ExperimentModel.__table__.delete())
        await db.execute(ExperimentDatasetItemModel.__table__.delete())
        await db.commit()


@pytest_asyncio.fixture(loop_scope="module")
async def store() -> ExperimentStore:
    return ExperimentStore()


@pytest.mark.asyncio(loop_scope="module")
class TestExperimentStore:
    """ExperimentStore direct integration tests."""

    async def test_save_and_get_experiment(self, store: ExperimentStore, clean_tables: None) -> None:
        eid = str(uuid4())
        m = ExperimentModel(
            id=eid,
            name="Test experiment",
            status="pending",
            evaluator_type="rule_based",
            dataset_item_ids='["item-1", "item-2"]',
        )
        saved = await store.save_experiment(m)
        assert saved is not None
        assert saved.id == eid

        got = await store.get_experiment(eid)
        assert got is not None
        assert got.name == "Test experiment"
        assert got.status == "pending"

    async def test_get_experiment_not_found(self, store: ExperimentStore, clean_tables: None) -> None:
        assert await store.get_experiment("nonexistent") is None

    async def test_list_experiments(self, store: ExperimentStore, clean_tables: None) -> None:
        for i in range(3):
            await store.save_experiment(ExperimentModel(
                id=str(uuid4()), name=f"Exp {i}", status="completed",
            ))

        items, total = await store.list_experiments()
        assert total == 3
        assert len(items) == 3

        completed, ct = await store.list_experiments(status="completed")
        assert ct == 3

        pending, pt = await store.list_experiments(status="pending")
        assert pt == 0

    async def test_save_and_get_run(self, store: ExperimentStore, clean_tables: None) -> None:
        eid = str(uuid4())
        await store.save_experiment(ExperimentModel(id=eid, name="Exp"))

        rid = str(uuid4())
        run = ExperimentRunModel(
            id=rid,
            experiment_id=eid,
            status="completed",
            total_items=5,
            passed_items=3,
            avg_score=0.6,
            results=[{"item_id": "i1", "passed": True}],
        )
        saved = await store.save_run(run)
        assert saved is not None
        assert saved.id == rid

        got = await store.get_run(rid)
        assert got is not None
        assert got.status == "completed"
        assert got.total_items == 5
        assert got.passed_items == 3

    async def test_list_runs_by_experiment(self, store: ExperimentStore, clean_tables: None) -> None:
        eid = str(uuid4())
        await store.save_experiment(ExperimentModel(id=eid, name="Exp"))
        for i in range(3):
            await store.save_run(ExperimentRunModel(
                id=str(uuid4()), experiment_id=eid, total_items=i,
            ))

        items, total = await store.list_runs_by_experiment(eid)
        assert total == 3
        assert len(items) == 3


@pytest.mark.asyncio(loop_scope="module")
class TestExperimentService:
    """ExperimentService integration tests."""

    async def test_create_and_get(self, clean_tables: None) -> None:
        service = ExperimentService()
        req = ExperimentCreate(
            name="质量回归测试",
            description="验证筛选质量",
            dataset_item_ids=["item-1", "item-2"],
            evaluator_type="rule_based",
            tags=["regression", "screening"],
        )
        result = await service.create_experiment(req, created_by="user-1")
        assert result is not None
        assert result.name == "质量回归测试"
        assert result.status == "pending"
        assert "item-1" in result.dataset_item_ids
        assert "regression" in result.tags

        got = await service.get_experiment(result.id)
        assert got is not None
        assert got.name == result.name

    async def test_list_experiments(self, clean_tables: None) -> None:
        service = ExperimentService()
        for i in range(3):
            await service.create_experiment(ExperimentCreate(name=f"Exp {i}"))

        items, total = await service.list_experiments()
        assert total == 3

    async def test_run_rule_based_empty(self, clean_tables: None) -> None:
        """运行一个没有 dataset items 的实验。"""
        service = ExperimentService()
        exp = await service.create_experiment(ExperimentCreate(name="Empty experiment"))
        assert exp is not None

        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.status == "completed"
        assert run.total_items == 0

    async def test_run_rule_basic_scoring(self, clean_tables: None) -> None:
        """创建一个含 dataset items 的实验并执行 rule_based 评估。"""
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()

        # 创建 2 个 dataset items
        items = []
        for score, expected, actual in [
            (0.8, {"decision": "advance"}, {"decision": "advance"}),
            (0.2, {"decision": "advance"}, {"decision": "reject"}),
        ]:
            item = ExperimentDatasetItemModel(
                id=str(uuid4()),
                category="screening",
                source="bad_case",
                score=score,
                expected_output=expected,
                actual_output=actual,
            )
            saved = await ds.save(item)
            if saved:
                items.append(saved.id)

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(name="Screening quality", dataset_item_ids=items),
        )
        assert exp is not None

        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.status == "completed"
        assert run.total_items == 2

        # 第一个 expected=actual → passed
        # 第二个 expected != actual → failed (score=0)
        assert run.passed_items == 1
        assert run.failed_items == 1

        # 验证运行记录可查
        runs_list, total = await service.list_runs(exp.id)
        assert total == 1
        assert runs_list[0].id == run.id

        # 验证运行详情
        run_detail = await service.get_run(run.id)
        assert run_detail is not None
        assert run_detail.total_items == 2

    async def test_run_without_expected_output(self, clean_tables: None) -> None:
        """没有预期输出的 item 使用 score 作为阈值。"""
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="conversation",
            source="manual",
            score=0.9,
        )
        saved = await ds.save(item)
        assert saved is not None

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(name="Score-based test", dataset_item_ids=[saved.id]),
        )
        assert exp is not None

        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.status == "completed"
        assert run.total_items == 1
        assert run.passed_items == 1
        assert run.avg_score == 0.9

    async def test_run_not_found(self, clean_tables: None) -> None:
        service = ExperimentService()
        result = await service.run_experiment("nonexistent")
        assert result is None

    # ════════════════════════════════════════════════════════════
    # agentops_evals evaluator integration tests
    # ════════════════════════════════════════════════════════════

    async def test_run_agentops_evals_screening(self, clean_tables: None) -> None:
        """agentops_evals + screening: 应触发 ScreeningReasonabilityEvaluator。"""
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="screening",
            source="bad_case",
            score=0.5,
            expected_output={"decision": "advance"},
            actual_output={"decision": "advance", "duration_ms": 500},
            input_snapshot={"model": "gpt-4", "prompt": "screen this candidate"},
        )
        saved = await ds.save(item)
        assert saved is not None

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(name="agentops-eval-screening", dataset_item_ids=[saved.id],
                             evaluator_type="agentops_evals"),
        )
        assert exp is not None

        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.status == "completed"
        assert run.total_items == 1
        # 至少有几个 evaluator 命中: Screening + 其他通用 evaluator
        assert len(run.results) == 1
        item_result = run.results[0]
        assert "evaluations" in item_result
        # 应该至少包含 screening.reasonability 打分
        eval_names = [e["score_name"] for e in item_result["evaluations"]]
        assert "screening.reasonability" in eval_names

    async def test_run_agentops_evals_resume_parse(self, clean_tables: None) -> None:
        """agentops_evals + resume_parse: 应触发 ResumeParseQualityEvaluator。"""
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="resume_parse",
            source="manual",
            score=0.8,
            actual_output={
                "name": "张三",
                "email": "z@t.com",
                "skills": ["Python", "FastAPI"],
                "experience_years": 5,
                "duration_ms": 200,
            },
            input_snapshot={"model": "gpt-4"},
        )
        saved = await ds.save(item)
        assert saved is not None

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(name="agentops-eval-resume", dataset_item_ids=[saved.id],
                             evaluator_type="agentops_evals"),
        )
        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.total_items == 1
        item_result = run.results[0]
        eval_names = [e["score_name"] for e in item_result["evaluations"]]
        assert "resume_parse.quality" in eval_names
        assert item_result["score"] > 0  # resume 字段齐全

    async def test_run_agentops_evals_tool_call(self, clean_tables: None) -> None:
        """agentops_evals + tool_call: 应触发 ToolSuccessEvaluator。"""
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="tool_call",
            source="auto",
            score=1.0,
            actual_output={
                "tool_name": "parse_resume",
                "tool_category": "resume_parser",
                "args": {"file_id": "abc"},
                "result": {"name": "张三"},
                "duration_ms": 1500,
            },
        )
        saved = await ds.save(item)
        assert saved is not None

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(name="agentops-eval-tool", dataset_item_ids=[saved.id],
                             evaluator_type="agentops_evals"),
        )
        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.total_items == 1
        item_result = run.results[0]
        eval_names = [e["score_name"] for e in item_result["evaluations"]]
        assert "tool.success" in eval_names

    async def test_run_agentops_evals_tool_error(self, clean_tables: None) -> None:
        """agentops_evals + tool 失败 → ToolSuccessEvaluator 打 0 分。"""
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="tool_call",
            source="auto",
            score=0.0,
            actual_output={
                "tool_name": "parse_resume",
                "tool_category": "resume_parser",
                "args": {"file_id": "abc"},
                "error": "connection refused",
                "duration_ms": 30000,
            },
        )
        saved = await ds.save(item)
        assert saved is not None

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(name="agentops-eval-tool-fail", dataset_item_ids=[saved.id],
                             evaluator_type="agentops_evals"),
        )
        run = await service.run_experiment(exp.id)
        assert run is not None
        item_result = run.results[0]
        # ToolSuccess 应该打 0
        tool_evals = [e for e in item_result["evaluations"] if e["score_name"] == "tool.success"]
        assert len(tool_evals) == 1
        assert tool_evals[0]["value"] == 0.0

    async def test_run_agentops_evals_conversation(self, clean_tables: None) -> None:
        """agentops_evals + conversation: 应触发 ConversationHelpfulnessEvaluator。"""
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="conversation",
            source="manual",
            score=0.7,
            actual_output={"response": "I recommend this candidate", "duration_ms": 800},
        )
        saved = await ds.save(item)
        assert saved is not None

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(name="agentops-eval-conv", dataset_item_ids=[saved.id],
                             evaluator_type="agentops_evals"),
        )
        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.total_items == 1
        item_result = run.results[0]
        eval_names = [e["score_name"] for e in item_result["evaluations"]]
        assert "conversation.helpfulness" in eval_names

    async def test_run_agentops_evals_unknown_fallback(self, clean_tables: None) -> None:
        """agentops_evals + 未知 category → fallback 到 rule_based。"""
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="unknown_category",
            source="manual",
            score=0.6,
            expected_output={"result": "ok"},
            actual_output={"result": "ok"},
        )
        saved = await ds.save(item)
        assert saved is not None

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(name="agentops-eval-unknown", dataset_item_ids=[saved.id],
                             evaluator_type="agentops_evals"),
        )
        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.total_items == 1
        # 应该有 fallback 的 evaluation
        item_result = run.results[0]
        assert len(item_result["evaluations"]) >= 1
        assert item_result["score"] == 1.0  # expected==actual


# ════════════════════════════════════════════════════════════
# _item_to_events unit tests
# ════════════════════════════════════════════════════════════


class TestItemToEvents:
    """_item_to_events 静态方法单元测试。"""

    def test_screening_creates_llm_event(self) -> None:
        from app.agentops.dataset.experiment_service import ExperimentService

        class FakeItem:
            category = "screening"
            actual_output = {"decision": "advance", "duration_ms": 100}
            input_snapshot = {"model": "gpt-4"}

        events = ExperimentService._item_to_events(FakeItem())
        assert len(events) == 1
        assert events[0].name == "screening"
        assert hasattr(events[0], "duration_ms")
        assert events[0].duration_ms == 100.0

    def test_resume_creates_llm_event(self) -> None:
        from app.agentops.dataset.experiment_service import ExperimentService

        class FakeItem:
            category = "resume_parse"
            actual_output = {"name": "张三", "skills": ["Python"]}
            input_snapshot = {}

        events = ExperimentService._item_to_events(FakeItem())
        assert len(events) == 1
        assert events[0].name == "resume_parse"

    def test_tool_creates_tool_event(self) -> None:
        from app.agentops.dataset.experiment_service import ExperimentService

        class FakeItem:
            category = "tool_call"
            actual_output = {"tool_name": "search", "args": {}, "result": {"ok": True}}
            input_snapshot = {}

        events = ExperimentService._item_to_events(FakeItem())
        assert len(events) == 1
        assert events[0].name == "search"
        from app.agentops.core.schemas import ToolInvocationEvent
        assert isinstance(events[0], ToolInvocationEvent)

    def test_conversation_creates_llm_event(self) -> None:
        from app.agentops.dataset.experiment_service import ExperimentService

        class FakeItem:
            category = "conversation"
            actual_output = {"response": "hello"}
            input_snapshot = {}

        events = ExperimentService._item_to_events(FakeItem())
        assert len(events) == 1
        assert events[0].name == "final_response"

    def test_unknown_category_no_event(self) -> None:
        from app.agentops.dataset.experiment_service import ExperimentService

        class FakeItem:
            category = "onboarding"  # not in mapping
            actual_output = {}
            input_snapshot = {}

        events = ExperimentService._item_to_events(FakeItem())
        assert events == []


# ════════════════════════════════════════════════════════════
# Comparison mode tests
# ════════════════════════════════════════════════════════════


@pytest.mark.asyncio(loop_scope="module")
class TestExperimentComparison:
    """compare_variants 集成测试。"""

    async def test_compare_no_variants(self, clean_tables: None) -> None:
        service = ExperimentService()
        exp = await service.create_experiment(ExperimentCreate(name="No variants"))
        assert exp is not None

        result = await service.compare_variants(exp.id)
        assert result is not None
        assert result.experiment_id == exp.id
        # 无 variant 时自动创建默认 variant
        assert len(result.comparisons) == 1

    async def test_compare_multiple_variants(self, clean_tables: None) -> None:
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="screening",
            source="bad_case",
            score=0.5,
            expected_output={"decision": "advance"},
            actual_output={"decision": "advance"},
        )
        saved = await ds.save(item)
        assert saved is not None

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(
                name="Compare variants",
                dataset_item_ids=[saved.id],
                variants=[{"version": "v1"}, {"version": "v2"}],
            ),
        )
        assert exp is not None

        result = await service.compare_variants(exp.id)
        assert result is not None
        assert result.experiment_name == "Compare variants"
        assert len(result.comparisons) == 2
        assert result.comparisons[0].variant_index == 0
        assert result.comparisons[1].variant_index == 1
        # 两个 variant 使用相同数据，分数应该相同
        assert result.comparisons[0].avg_score == result.comparisons[1].avg_score
        assert result.comparisons[0].status == "completed"
        assert result.comparisons[1].status == "completed"
        assert result.score_delta >= 0

    async def test_compare_not_found(self, clean_tables: None) -> None:
        service = ExperimentService()
        result = await service.compare_variants("nonexistent")
        assert result is None

    async def test_compare_with_three_variants(self, clean_tables: None) -> None:
        from app.agentops.dataset.models import DatasetStore

        ds = DatasetStore()
        items = []
        for i in range(3):
            item = ExperimentDatasetItemModel(
                id=str(uuid4()),
                category="screening",
                source="manual",
                score=0.5,
                expected_output={"decision": "advance"},
                actual_output={"decision": "advance"},
            )
            saved = await ds.save(item)
            if saved:
                items.append(saved.id)

        service = ExperimentService()
        exp = await service.create_experiment(
            ExperimentCreate(
                name="Three variants",
                dataset_item_ids=items,
                variants=[{"model": "gpt-4"}, {"model": "gpt-3.5"}, {"model": "claude-3"}],
            ),
        )
        assert exp is not None

        result = await service.compare_variants(exp.id)
        assert result is not None
        assert len(result.comparisons) == 3
        # variant 0 有最佳分数（至少不差于其他）
        assert result.best_variant_index in (0, 1, 2)
        assert result.best_score >= 0

    async def test_compare_router_endpoint(self, clean_tables: None) -> None:
        """验证路由存在且 schema 正确。"""
        from app.agentops.dataset.experiment_router import router

        routes = [r.path for r in router.routes]
        assert "/api/v1/agentops/dataset/experiments/{experiment_id}/compare" in routes
