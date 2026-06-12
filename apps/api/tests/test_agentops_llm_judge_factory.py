"""Tests for LLMJudgeFactory (Phase A, P2-C).

Covers:
- Factory disabled/enabled
- Client reuse + model override
- Fallback chain (timeout → HeuristicJudge, LLM error → HeuristicJudge)
- Factory init failure safe fallback
- ExperimentService injection
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agentops.evaluation import HeuristicJudge, LLMJudgeFactory, MockJudge, PromptBasedJudge


class FakeSettings:
    llm_judge_enabled: bool = False
    llm_judge_model: str = "gpt-4o-mini"
    llm_judge_timeout: float = 15.0
    llm_judge_fallback: str = "heuristic"
    llm_provider: str = "omlx"


class TestFactoryDisabled:
    def test_disabled_returns_heuristic(self) -> None:
        s = FakeSettings()
        s.llm_judge_enabled = False
        assert isinstance(LLMJudgeFactory.from_settings(s), HeuristicJudge)

    def test_default_is_disabled(self) -> None:
        assert isinstance(LLMJudgeFactory.from_settings(FakeSettings()), HeuristicJudge)


class TestFactoryEnabled:
    def test_enabled_returns_prompt_based_judge(self) -> None:
        s = FakeSettings()
        s.llm_judge_enabled = True
        with patch("app.llm.get_llm_client") as mock_get:
            mock_get.return_value.chat = AsyncMock(return_value='{"overall": 0.9}')
            judge = LLMJudgeFactory.from_settings(s)
            assert isinstance(judge, PromptBasedJudge)

    def test_judge_fn_passes_model_override(self) -> None:
        """judge_fn 调用 chat() 时传入了 llm_judge_model。"""
        s = FakeSettings()
        s.llm_judge_enabled = True
        s.llm_judge_model = "judge-model-v1"

        chat_mock = AsyncMock(return_value='{"overall": 0.85}')

        with patch("app.llm.get_llm_client") as mock_get:
            mock_get.return_value.chat = chat_mock
            judge = LLMJudgeFactory.from_settings(s)
            assert isinstance(judge, PromptBasedJudge)

            import asyncio
            scores, _ = asyncio.run(judge.judge("{input_text} {output_text}", "in", "out"))
            assert scores["overall"] == 0.85

            call_kwargs = chat_mock.await_args
            assert call_kwargs is not None
            assert call_kwargs[1].get("model") == "judge-model-v1"

    def test_judge_fn_sends_user_message(self) -> None:
        s = FakeSettings()
        s.llm_judge_enabled = True
        chat_mock = AsyncMock(return_value='{"overall": 0.9}')

        with patch("app.llm.get_llm_client") as mock_get:
            mock_get.return_value.chat = chat_mock
            judge = LLMJudgeFactory.from_settings(s)
            import asyncio
            asyncio.run(judge.judge("{input_text} {output_text}", "in", "out"))
            messages = chat_mock.await_args[0][0]
            assert messages[0]["role"] == "user"


class TestFallbackChain:
    async def test_timeout_fallsback_to_heuristic(self) -> None:
        async def timeout_judge(prompt: str) -> str:
            raise __import__("asyncio").TimeoutError("timeout")

        judge = PromptBasedJudge(timeout_judge)
        scores, reasoning = await judge.judge("{input_text} {output_text}", "in", "out")
        assert "heuristic" in reasoning.lower() or "length" in reasoning.lower()

    async def test_llm_error_fallsback(self) -> None:
        async def broken_judge(prompt: str) -> str:
            raise RuntimeError("LLM down")

        judge = PromptBasedJudge(broken_judge)
        scores, reasoning = await judge.judge("{input_text} {output_text}", "in", "out")
        assert scores["overall"] < 0.5

    async def test_factory_init_failure_fallsback(self) -> None:
        s = FakeSettings()
        s.llm_judge_enabled = True
        with patch("app.llm.get_llm_client", side_effect=RuntimeError("no LLM")):
            judge = LLMJudgeFactory.from_settings(s)
            assert isinstance(judge, HeuristicJudge)


class TestExperimentServiceInjection:
    async def test_experiment_service_accepts_judge_backend(self) -> None:
        from app.agentops.dataset.experiment_service import ExperimentService

        judge = MockJudge(fixed_overall=0.75)
        service = ExperimentService(judge_backend=judge)
        assert service._judge_backend is judge

    async def test_agentops_evals_uses_injected_judge(self) -> None:
        from uuid import uuid4

        from app.agentops.dataset.experiment_schemas import ExperimentCreate
        from app.agentops.dataset.experiment_service import ExperimentService
        from app.agentops.dataset.models import DatasetStore, ExperimentDatasetItemModel
        from app.agentops.evaluation import MockJudge

        ds = DatasetStore()
        item = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category="screening",
            source="manual",
            score=0.5,
            expected_output={"decision": "advance"},
            actual_output={"decision": "advance", "duration_ms": 100},
            input_snapshot={"model": "gpt-4"},
        )
        saved = await ds.save(item)
        assert saved is not None

        judge = MockJudge(fixed_overall=0.75)
        service = ExperimentService(judge_backend=judge)

        exp = await service.create_experiment(
            ExperimentCreate(name="JudgeInject", dataset_item_ids=[saved.id],
                             evaluator_type="agentops_evals"),
        )
        assert exp is not None

        run = await service.run_experiment(exp.id)
        assert run is not None
        assert run.status == "completed"
        assert run.total_items == 1

        item_result = run.results[0]
        screening_evals = [
            e for e in item_result.get("evaluations", [])
            if e["score_name"] == "screening.reasonability"
        ]
        assert len(screening_evals) == 1
        assert screening_evals[0]["value"] == 0.75
        assert screening_evals[0]["source"] == "llm_judge"
