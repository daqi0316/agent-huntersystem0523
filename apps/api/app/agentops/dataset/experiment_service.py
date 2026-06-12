"""ExperimentService — 实验业务逻辑。

职责：
- 创建/查询实验定义
- 执行实验（基于 dataset items + evaluator + variant）
- 记录运行结果
- 统计与对比
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from app.agentops.core.schemas import (
    BaseEvent,
    EventType,
    LLMGenerationEvent,
    SpanEvent,
    ToolInvocationEvent,
)
from app.agentops.dataset.experiment_models import ExperimentModel, ExperimentRunModel, ExperimentStore
from app.agentops.dataset.experiment_schemas import (
    ExperimentComparisonResponse,
    ExperimentCreate,
    ExperimentResponse,
    ExperimentRunResponse,
    ExperimentRunSummaryResponse,
    VariantComparison,
)
from app.agentops.dataset.schemas import DatasetItemCreate, DatasetItemSource
from app.agentops.evaluation import EvaluationResult, ScoreType, ScoreWriter, run_all_evaluators


class ExperimentService:
    """实验业务逻辑层。"""

    def __init__(self, store: ExperimentStore | None = None, *, judge_backend=None):
        self.store = store or ExperimentStore()
        self._judge_backend = judge_backend

    async def create_experiment(
        self, req: ExperimentCreate, *, created_by: str = "",
    ) -> ExperimentResponse | None:
        """创建一条实验定义。"""
        model = ExperimentModel(
            id=str(uuid4()),
            name=req.name,
            description=req.description or None,
            status="pending",
            dataset_item_ids=json.dumps(req.dataset_item_ids, ensure_ascii=False) if req.dataset_item_ids else None,
            evaluator_type=req.evaluator_type,
            evaluator_config=req.evaluator_config or None,
            variants=req.variants if req.variants else None,
            tags=json.dumps(req.tags, ensure_ascii=False) if req.tags else None,
            created_by=created_by or None,
        )
        saved = await self.store.save_experiment(model)
        return saved.to_response() if saved else None

    async def get_experiment(self, experiment_id: str) -> ExperimentResponse | None:
        model = await self.store.get_experiment(experiment_id)
        return model.to_response() if model else None

    async def list_experiments(
        self, *, status: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ExperimentResponse], int]:
        items, total = await self.store.list_experiments(status=status, limit=limit, offset=offset)
        return [item.to_response() for item in items], total

    async def run_experiment(
        self, experiment_id: str, *, variant_index: int = 0,
    ) -> ExperimentRunResponse | None:
        """执行一次实验运行（同步模式：逐项评估并返回结果）。

        支持三种 evaluator_type:
        - rule_based (默认): 比较 expected_output 与 actual_output 字段精确匹配。
        - agentops_evals: 使用 Evaluation 模块的 8 个评估器 (ToolSuccess, Latency,
          PII Safety, Intent Correctness, ResumeParse, Screening, JD, Conversation)。
        - llm_judge / comparison: 预留。
        """
        experiment = await self.store.get_experiment(experiment_id)
        if not experiment:
            return None

        experiment.status = "running"
        await self.store.save_experiment(experiment)

        item_ids = json.loads(experiment.dataset_item_ids) if experiment.dataset_item_ids else []
        from app.agentops.dataset.models import DatasetStore
        ds = DatasetStore()

        run_id = str(uuid4())
        results: list[dict] = []
        total_score = 0.0
        passed = 0
        failed = 0

        started_at = datetime.now(UTC)
        start_ts = time.time()

        for item_id in item_ids:
            item = await ds.get(item_id)
            if not item:
                continue

            item_result: dict = {
                "item_id": item_id,
                "category": item.category,
                "score": 0.0,
                "passed": False,
                "errors": [],
                "evaluations": [],
            }

            try:
                if experiment.evaluator_type == "agentops_evals":
                    score, eval_results = await self._evaluate_with_agentops_evals(item, judge_backend=self._judge_backend)
                    item_result["evaluations"] = [
                        {"score_name": r.score_name, "value": r.value, "source": r.source, "comment": r.comment}
                        for r in eval_results
                    ]
                    item_result["score"] = round(score, 4)
                    item_result["passed"] = score >= 0.5
                elif experiment.evaluator_type == "rule_based":
                    score = await self._evaluate_with_rule_based(item)
                    item_result["score"] = round(score, 4)
                    item_result["passed"] = score >= 0.5
                else:
                    item_result["score"] = 0.0
                    item_result["passed"] = False
                    item_result["errors"].append(f"evaluator_type '{experiment.evaluator_type}' not implemented")

                if item_result["passed"]:
                    passed += 1
                else:
                    failed += 1
                total_score += item_result["score"]

            except Exception as e:
                item_result["errors"].append(str(e))
                failed += 1

            results.append(item_result)

        duration_ms = round((time.time() - start_ts) * 1000, 2)
        completed_at = datetime.now(UTC)
        total_items = len(results)
        avg_score = round(total_score / total_items, 4) if total_items > 0 else 0.0

        run = ExperimentRunModel(
            id=run_id,
            experiment_id=experiment_id,
            variant_index=variant_index,
            status="completed",
            total_items=total_items,
            passed_items=passed,
            failed_items=failed,
            avg_score=avg_score,
            results=results,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )
        saved = await self.store.save_run(run)

        experiment.status = "completed"
        await self.store.save_experiment(experiment)

        return saved.to_response() if saved else None

    @staticmethod
    async def _evaluate_with_rule_based(item: object) -> float:
        """rule_based 评估：比较 expected_output 与 actual_output 字段精确匹配。"""
        expected = getattr(item, "expected_output", None) or {}
        actual = getattr(item, "actual_output", None) or {}

        if not expected:
            return getattr(item, "score", 0.0)

        matched = 0
        total_fields = len(expected)
        for k, v in expected.items():
            if k in actual and actual[k] == v:
                matched += 1
        return matched / total_fields if total_fields > 0 else 1.0

    @staticmethod
    def _item_to_events(item: object) -> list[BaseEvent]:
        """将 dataset item 转换为 Evaluation 模块可消费的事件列表。

        根据 item.category 创建对应类型的 BaseEvent，让 evaluator 可以处理。
        """
        category = getattr(item, "category", "") or ""
        actual = getattr(item, "actual_output", None) or {}
        input_data = getattr(item, "input_snapshot", None) or {}
        events: list[BaseEvent] = []

        if category in ("resume_parse", "resume"):
            events.append(LLMGenerationEvent(
                name="resume_parse",
                event_type=EventType.LLM_GENERATION_COMPLETED,
                output=actual,
                input=input_data,
                model=input_data.get("model", "experiment"),
                prompt_tokens=0,
                completion_tokens=0,
            ))
        elif category in ("screening", "screen"):
            events.append(LLMGenerationEvent(
                name="screening",
                event_type=EventType.LLM_GENERATION_COMPLETED,
                output=actual,
                input=input_data,
                model=input_data.get("model", "experiment"),
                prompt_tokens=0,
                completion_tokens=0,
            ))
        elif category in ("jd_generation", "jd"):
            events.append(LLMGenerationEvent(
                name="jd_generation",
                event_type=EventType.LLM_GENERATION_COMPLETED,
                output=actual,
                input=input_data,
                model=input_data.get("model", "experiment"),
                prompt_tokens=0,
                completion_tokens=0,
            ))
        elif category in ("tool_call", "tool"):
            is_error = actual.get("error") is not None
            events.append(ToolInvocationEvent(
                name=actual.get("tool_name", "experiment_tool"),
                event_type=EventType.TOOL_INVOCATION_FAILED if is_error else EventType.TOOL_INVOCATION_COMPLETED,
                tool_name=actual.get("tool_name", "experiment_tool"),
                tool_category=actual.get("tool_category", "experiment"),
                success=not is_error,
                error=actual.get("error", ""),
                input=actual.get("args", {}),
                output=actual.get("result", {}),
            ))
        elif category in ("conversation", "chat", "helpfulness"):
            events.append(LLMGenerationEvent(
                name="final_response",
                event_type=EventType.LLM_GENERATION_COMPLETED,
                output=actual,
                input=input_data,
                model=input_data.get("model", "experiment"),
                prompt_tokens=0,
                completion_tokens=0,
            ))

        # 所有事件都加上 duration_ms 以支持 LatencyEvaluator
        duration = actual.get("duration_ms")
        if duration is not None:
            for ev in events:
                ev.duration_ms = float(duration)

        return events

    @staticmethod
    async def _evaluate_with_agentops_evals(
        item: object, *, judge_backend=None,
    ) -> tuple[float, list[EvaluationResult]]:
        """agentops_evals 评估：使用 Evaluation 模块的评估器。

        当 judge_backend 提供时，注入到 4 个 LLM judge evaluator 中。
        否则使用 heuristic/默认行为。

        返回:
            (avg_score, evaluation_results): 各评估器的平均分和详细结果。
        """
        events = ExperimentService._item_to_events(item)
        if not events:
            score = await ExperimentService._evaluate_with_rule_based(item)
            return score, [
                EvaluationResult(
                    score_name="experiment.fallback",
                    value=score,
                    comment=f"No events generated for category '{getattr(item, 'category', '')}'",
                    source="rule",
                )
            ]

        from app.agentops.evaluation import evaluators as ev

        eval_list = [
            ev.ToolSuccessEvaluator(),
            ev.LatencyEvaluator(),
            ev.PIISafetyEvaluator(),
            ev.IntentCorrectnessEvaluator(),
            ev.ResumeParseQualityEvaluator(judge_backend=judge_backend),
            ev.ScreeningReasonabilityEvaluator(judge_backend=judge_backend),
            ev.JDQualityEvaluator(judge_backend=judge_backend),
            ev.ConversationHelpfulnessEvaluator(judge_backend=judge_backend),
        ]
        results = await run_all_evaluators(events, evaluators=eval_list)
        if not results:
            # 没有评估器匹配，回退
            score = await ExperimentService._evaluate_with_rule_based(item)
            results = [
                EvaluationResult(
                    score_name="experiment.fallback",
                    value=score,
                    comment="No evaluators matched; fell back to field comparison",
                    source="rule",
                )
            ]

        avg_score = sum(r.value for r in results) / len(results)
        return avg_score, results

    async def get_run(self, run_id: str) -> ExperimentRunResponse | None:
        model = await self.store.get_run(run_id)
        return model.to_response() if model else None

    async def list_runs(
        self, experiment_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ExperimentRunSummaryResponse], int]:
        items, total = await self.store.list_runs_by_experiment(
            experiment_id, limit=limit, offset=offset,
        )
        return [item.to_summary() for item in items], total

    async def compare_variants(
        self, experiment_id: str,
    ) -> ExperimentComparisonResponse | None:
        """运行所有 variant 并返回对比结果。"""
        experiment = await self.store.get_experiment(experiment_id)
        if not experiment:
            return None

        variants = experiment.variants if isinstance(experiment.variants, list) else []
        if not variants:
            # 无 variant 时当作只有一个默认 variant
            variants = [{}]

        comparisons: list[VariantComparison] = []
        best_idx = 0
        best_score = -1.0

        for idx, variant in enumerate(variants):
            run = await self.run_experiment(experiment_id, variant_index=idx)
            if run is None:
                comparisons.append(VariantComparison(
                    variant_index=idx, variant_config=variant,
                    status="failed", avg_score=0.0,
                ))
                continue

            score = run.avg_score
            if score > best_score:
                best_score = score
                best_idx = idx

            comparisons.append(VariantComparison(
                variant_index=idx,
                variant_config=variant,
                avg_score=score,
                total_items=run.total_items,
                passed_items=run.passed_items,
                failed_items=run.failed_items,
                duration_ms=run.duration_ms,
                run_id=run.id,
                status=run.status,
            ))

        scores = [c.avg_score for c in comparisons if c.status == "completed"]
        score_delta = round(max(scores) - min(scores), 4) if len(scores) > 1 else 0.0

        return ExperimentComparisonResponse(
            experiment_id=experiment_id,
            experiment_name=experiment.name,
            best_variant_index=best_idx,
            best_score=round(best_score, 4),
            score_delta=score_delta,
            comparisons=comparisons,
        )
