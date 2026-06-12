"""DatasetService — dataset item 业务逻辑。

职责：
- 创建/查询/删除 dataset item
- 从反馈生成 dataset item（bad case / annotation → dataset）
- 统计
"""

from __future__ import annotations

from uuid import uuid4

from app.agentops.dataset.models import DatasetStore, ExperimentDatasetItemModel
from app.agentops.dataset.schemas import DatasetItemCreate, DatasetItemResponse, DatasetStats
from app.agentops.feedback.schemas import FeedbackCategory
from app.core.database import AsyncSessionLocal


class DatasetService:
    """Dataset item 业务逻辑层。"""

    def __init__(self, store: DatasetStore | None = None):
        self.store = store or DatasetStore()

    async def create_item(self, req: DatasetItemCreate) -> DatasetItemResponse | None:
        """创建一条 dataset item。"""
        model = ExperimentDatasetItemModel(
            id=str(uuid4()),
            category=req.category.value if hasattr(req.category, "value") else str(req.category),
            source=req.source.value if hasattr(req.source, "value") else str(req.source),
            trace_id=req.trace_id or None,
            span_id=req.span_id or None,
            session_id=req.session_id or None,
            entity_type=req.entity_type or None,
            entity_id=req.entity_id or None,
            input_snapshot=req.input_snapshot or None,
            expected_output=req.expected_output or None,
            actual_output=req.actual_output or None,
            feedback_id=req.feedback_id or None,
            tags=__import__("json").dumps(req.tags, ensure_ascii=False) if req.tags else None,
            is_bad_case=req.is_bad_case,
            description=req.description or None,
            corrected_output=req.corrected_output,
            correction_notes=req.correction_notes or None,
            priority=req.priority,
            score=req.score,
            metadata_json=req.metadata or None,
        )
        saved = await self.store.save(model)
        return saved.to_response() if saved else None

    async def get_item(self, item_id: str) -> DatasetItemResponse | None:
        """按 ID 查询。"""
        model = await self.store.get(item_id)
        return model.to_response() if model else None

    async def list_items(
        self,
        *,
        category: str | None = None,
        source: str | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        feedback_id: str | None = None,
        is_bad_case: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DatasetItemResponse], int]:
        """查询 dataset item 列表。"""
        items, total = await self.store.list(
            category=category,
            source=source,
            trace_id=trace_id,
            session_id=session_id,
            entity_type=entity_type,
            entity_id=entity_id,
            feedback_id=feedback_id,
            is_bad_case=is_bad_case,
            limit=limit,
            offset=offset,
        )
        return [item.to_response() for item in items], total

    async def delete_item(self, item_id: str) -> bool:
        """删除一条 dataset item。"""
        return await self.store.delete(item_id)

    async def get_stats(self) -> DatasetStats:
        """获取统计。"""
        return await self.store.stats()

    async def create_from_feedback(
        self,
        feedback_id: str,
        *,
        user_id: str | None = None,
    ) -> DatasetItemResponse | None:
        """从一条反馈（bad case）自动生成 dataset item。

        查找 feedback_id 对应的反馈，如果 source 属于自动标记 bad case
        的类型（annotator/auto_rule/auto_eval），则自动创建 dataset item。
        """
        from app.agentops.feedback.models import AgentFeedbackModel, FeedbackStore

        fb_store = FeedbackStore()
        feedback = await fb_store.get(feedback_id)
        if not feedback:
            return None

        # 自动标记 bad_case 的来源
        auto_bad_case_sources = {"annotator", "auto_rule", "auto_eval"}
        is_bad_case = feedback.source in auto_bad_case_sources

        mapping = {
            "tool_call": "tool_call",
            "custom": "other",
        }
        mapped_category = mapping.get(feedback.category, "conversation")

        req = DatasetItemCreate(
            category=mapped_category,  # type: ignore[arg-type]
            source="bad_case",
            trace_id=feedback.trace_id or "",
            span_id=feedback.span_id or "",
            session_id=feedback.session_id or "",
            entity_type=feedback.target_entity_type or "",
            entity_id=feedback.target_entity_id or "",
            feedback_id=feedback.id,
            expected_output={},  # 反馈不包含预期输出
            actual_output={"reason": feedback.reason} if feedback.reason else {},
            tags=(
                __import__("json").loads(feedback.tags)
                if feedback.tags
                else (["bad_case"] if is_bad_case else [])
            ),
            is_bad_case=is_bad_case,
            description=f"Auto-generated from feedback ({feedback.category}, score={feedback.score})",
            score=feedback.score,
            metadata={
                "feedback_source": feedback.source,
                "feedback_category": feedback.category,
                "feedback_score": feedback.score,
            },
        )
        return await self.create_item(req)
