"""DashboardMetrics — 看板数据聚合层 (P2-C Stage 14).

从 agentops 各模块聚合数据，供前端看板展示。
所有方法返回序列化友好的 dict，避免前端二次处理。
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agentops.privacy.sanitizer import sanitize_payload

logger = logging.getLogger(__name__)


class DashboardMetrics:
    """看板指标聚合器。

    从 ExperimentRun、Feedback、Dataset 等模块聚合数据。
    所有方法都是类方法，方便调用。
    """

    @classmethod
    async def overview(cls) -> dict[str, Any]:
        """系统概览：主要模块的统计数字。"""
        from app.agentops.dataset.experiment_models import ExperimentModel, ExperimentRunModel, ExperimentStore
        from app.agentops.dataset.models import DatasetStore
        from app.agentops.feedback.service import FeedbackService

        store = ExperimentStore()
        ds = DatasetStore()
        fb = FeedbackService()

        # 实验统计
        experiments, exp_total = await store.list_experiments(limit=1)
        runs_total = 0
        if exp_total > 0:
            all_exps, _ = await store.list_experiments(limit=10000)
            for exp in all_exps:
                _, rt = await store.list_runs_by_experiment(exp.id, limit=1)
                runs_total += rt

        # Dataset 统计
        ds_items, ds_total = await ds.list(limit=1)

        # Feedback 统计
        _, total_feedback = await fb.list_feedback(limit=1)

        return {
            "total_experiments": exp_total,
            "total_runs": runs_total,
            "total_dataset_items": ds_total,
            "total_feedback": total_feedback,
        }

    @classmethod
    async def quality_summary(cls) -> dict[str, Any]:
        """质量汇总：各分类的平均分、通过率、实验运行次数。"""
        from app.agentops.dataset.experiment_models import ExperimentModel, ExperimentRunModel, ExperimentStore

        store = ExperimentStore()

        all_exps, _ = await store.list_experiments(limit=10000)
        completed_exps = [e for e in all_exps if e.status == "completed"]

        category_scores: dict[str, list[float]] = {}
        total_runs = 0
        total_avg_score = 0.0
        total_passed = 0
        total_items = 0

        for exp in completed_exps:
            runs_list, _ = await store.list_runs_by_experiment(exp.id, limit=100)
            for run in runs_list:
                total_runs += 1
                total_avg_score += run.avg_score
                total_passed += run.passed_items
                total_items += run.total_items

                # 按 category 聚合（从 results 提取）
                if run.results:
                    for r in run.results if isinstance(run.results, list) else []:
                        cat = r.get("category", "unknown")
                        s = r.get("score", 0.0)
                        category_scores.setdefault(cat, []).append(s)

        avg_overall = round(total_avg_score / total_runs, 4) if total_runs > 0 else 0.0
        pass_rate = round(total_passed / total_items, 4) if total_items > 0 else 0.0

        category_avg = {
            cat: round(sum(scores) / len(scores), 4)
            for cat, scores in sorted(category_scores.items())
        }

        return {
            "avg_score": avg_overall,
            "pass_rate": pass_rate,
            "total_runs": total_runs,
            "total_items": total_items,
            "completed_experiments": len(completed_exps),
            "category_scores": category_avg,
        }

    @classmethod
    async def recent_runs(cls, limit: int = 20) -> list[dict[str, Any]]:
        """最近实验运行记录，含评估结果摘要。"""
        from app.agentops.dataset.experiment_models import ExperimentStore

        store = ExperimentStore()
        all_exps, _ = await store.list_experiments(limit=100)
        results: list[dict[str, Any]] = []

        for exp in all_exps:
            runs, _ = await store.list_runs_by_experiment(exp.id, limit=limit // max(len(all_exps), 1))
            for run in runs:
                results.append({
                    "run_id": run.id,
                    "experiment_name": exp.name,
                    "status": run.status,
                    "avg_score": run.avg_score,
                    "total_items": run.total_items,
                    "passed_items": run.passed_items,
                    "failed_items": run.failed_items,
                    "duration_ms": run.duration_ms,
                    "started_at": run.started_at.isoformat() if run.started_at else "",
                    "completed_at": run.completed_at.isoformat() if run.completed_at else "",
                })

        results.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return results[:limit]

    @classmethod
    async def evaluator_performance(cls) -> dict[str, dict[str, Any]]:
        """各评估器的性能统计：平均分、使用次数。"""
        from app.agentops.dataset.experiment_models import ExperimentStore

        store = ExperimentStore()
        all_exps, _ = await store.list_experiments(limit=10000)

        eval_stats: dict[str, list[float]] = {}
        eval_counts: dict[str, int] = {}

        for exp in all_exps:
            runs, _ = await store.list_runs_by_experiment(exp.id, limit=50)
            for run in runs:
                if not run.results:
                    continue
                for r in run.results if isinstance(run.results, list) else []:
                    evals = r.get("evaluations", [])
                    if not evals:
                        continue
                    for ev in evals:
                        name = ev.get("score_name", "unknown")
                        val = ev.get("value", 0.0)
                        eval_stats.setdefault(name, []).append(val)
                        eval_counts[name] = eval_counts.get(name, 0) + 1

        return {
            name: {
                "avg_score": round(sum(scores) / len(scores), 4),
                "count": eval_counts.get(name, 0),
                "min_score": round(min(scores), 4),
                "max_score": round(max(scores), 4),
            }
            for name, scores in sorted(eval_stats.items())
        }

    @classmethod
    async def feedback_summary(cls) -> dict[str, Any]:
        """反馈汇总：总数、各类分类的分布。"""
        from app.agentops.feedback.service import FeedbackService

        fb = FeedbackService()
        _, total = await fb.list_feedback(limit=1)

        # 按分类统计
        try:
            stats = await fb.get_stats()
            category_dist = stats.category_stats
        except Exception:
            category_dist = {}

        return {
            "total": total,
            "by_category": category_dist,
        }

    # ════════════════════════════════════════════════════════════
    # Phase C: Trace 瀑布图 + 成本时间趋势
    # ════════════════════════════════════════════════════════════

    @classmethod
    async def trace_detail(cls, trace_id: str) -> dict[str, Any] | None:
        """返回单个 trace 的完整事件链 + 时间线（已脱敏）。"""
        from app.agentops.events.store import EventStore

        store = EventStore()
        items, total = await store.list(trace_id=trace_id, limit=200)
        if total == 0:
            return None

        events = []
        base_time: str | None = None
        for item in items:
            d = item.to_dict()
            # PII 脱敏
            d["domain_fields"] = sanitize_payload(d.get("domain_fields", {}))
            if base_time is None:
                base_time = d["created_at"]
            d["offset_ms"] = _time_diff_ms(base_time, d["created_at"])
            events.append(d)

        return {
            "trace_id": trace_id,
            "event_count": total,
            "events": events,
        }

    @classmethod
    async def trace_search(
        cls,
        *,
        event_type: str = "",
        entity_type: str = "",
        entity_id: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        """搜索业务事件，支持按类型/实体过滤。"""
        from app.agentops.events.store import EventStore

        store = EventStore()
        items, total = await store.list(
            event_type=event_type or None,
            entity_type=entity_type or None,
            entity_id=entity_id or None,
            limit=limit,
        )
        return {"items": [i.to_dict() for i in items], "total": total}

    @classmethod
    async def cost_timeseries(cls, days: int = 30) -> dict[str, Any]:
        """按 started_at 日期聚合 experiment_run 数据。"""
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            stmt = text("""
                SELECT DATE(started_at) as day,
                       COUNT(*) as runs,
                       AVG(avg_score) as avg_score
                FROM agent_experiment_run
                WHERE started_at >= NOW() - INTERVAL ':days' DAY
                  AND status = 'completed'
                GROUP BY day
                ORDER BY day ASC
            """).bindparams(days=days)
            result = await db.execute(stmt)
            rows = result.all()

        daily = [
            {"date": str(r[0]), "runs": r[1], "avg_score": round(float(r[2]), 4)}
            for r in rows
        ]
        total_runs = sum(d["runs"] for d in daily)
        return {
            "daily": daily,
            "summary": {
                "total_runs": total_runs,
                "avg_score": round(
                    sum(d["avg_score"] * d["runs"] for d in daily) / total_runs, 4
                ) if total_runs > 0 else 0.0,
            },
        }


def _time_diff_ms(t1: str, t2: str) -> float:
    """计算两个 ISO 时间戳的毫秒差。"""
    fmt = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (fmt(t2) - fmt(t1)).total_seconds() * 1000
