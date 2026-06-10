"""P2-2: 公司专属招聘知识库服务 — CRUD + embedding 同步 + 生效期管理。"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func as sa_func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.qdrant import get_qdrant
from app.llm import get_llm_client
from app.models.company_knowledge import (
    CompanyRecruitingKnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeItemType,
)
from app.schemas.company_knowledge import (
    KnowledgeItemCreate,
    KnowledgeItemUpdate,
)

logger = logging.getLogger(__name__)

KNOWLEDGE_QDRANT_COLLECTION = "company_knowledge"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _now().date()


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class CompanyKnowledgeService:
    """公司招聘知识条目服务。

    职责：
    - 结构化知识 CRUD（PostgreSQL）
    - 向量同步（Qdrant）
    - 状态生命周期（draft → proposed → active → expired/archived）
    - 生效期过滤
    - AI 引用支持
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._llm_client = None
        self._qdrant = None

    @property
    def llm(self):
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client

    @property
    async def qdrant(self):
        if self._qdrant is None:
            self._qdrant = await get_qdrant()
        return self._qdrant

    # ── CRUD ─────────────────────────────────────────────────────────

    async def create(self, data: KnowledgeItemCreate) -> CompanyRecruitingKnowledgeItem:
        """创建知识条目，同步 embedding 到 Qdrant。"""
        item = CompanyRecruitingKnowledgeItem(
            id=str(uuid.uuid4()),
            org_id=data.org_id,
            job_profile_id=data.job_profile_id,
            knowledge_type=KnowledgeItemType(data.knowledge_type),
            status=KnowledgeItemStatus.PROPOSED if data.auto_generated else KnowledgeItemStatus.DRAFT,
            title=data.title,
            content=data.content,
            source=data.source,
            confidence=data.confidence,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            tags=data.tags,
            auto_generated=data.auto_generated,
            created_by=data.created_by,
        )
        self.db.add(item)
        await self.db.flush()

        # 如果是 auto_generated，同步 embedding
        if data.auto_generated:
            await self._sync_embedding(item)

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def get(self, item_id: str) -> CompanyRecruitingKnowledgeItem | None:
        if not _valid_uuid(item_id):
            return None
        result = await self.db.execute(
            select(CompanyRecruitingKnowledgeItem).where(
                CompanyRecruitingKnowledgeItem.id == item_id
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self, item_id: str, data: KnowledgeItemUpdate,
    ) -> CompanyRecruitingKnowledgeItem | None:
        """更新知识条目，必要时重新同步 embedding。"""
        item = await self.get(item_id)
        if item is None:
            return None

        changed = False
        if data.title is not None and data.title != item.title:
            item.title = data.title
            changed = True
        if data.content is not None and data.content != item.content:
            item.content = data.content
            changed = True
        if data.source is not None:
            item.source = data.source
        if data.confidence is not None:
            item.confidence = data.confidence
        if data.effective_from is not None:
            item.effective_from = data.effective_from
        if data.effective_to is not None:
            item.effective_to = data.effective_to
        if data.tags is not None:
            item.tags = data.tags

        # 状态变更
        if data.status is not None:
            new_status = KnowledgeItemStatus(data.status)
            self._validate_status_transition(item.status, new_status)
            item.status = new_status
            if new_status == KnowledgeItemStatus.ACTIVE:
                item.reviewed_at = _now()
            changed = True

        # 内容/标题变更 + active → 重新同步 embedding
        if changed and item.status == KnowledgeItemStatus.ACTIVE:
            await self._sync_embedding(item)
        elif changed and item.embedding_id:
            # 非 active 的内容变更 → 删除旧 embedding
            await self._remove_embedding(item.embedding_id)
            item.embedding_id = None

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete(self, item_id: str) -> bool:
        item = await self.get(item_id)
        if item is None:
            return False
        if item.embedding_id:
            await self._remove_embedding(item.embedding_id)
        await self.db.delete(item)
        await self.db.commit()
        return True

    # ── 查询 ──────────────────────────────────────────────────────────

    async def list(
        self,
        org_id: str,
        knowledge_type: str | None = None,
        status: str | None = None,
        job_profile_id: str | None = None,
        only_active: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[CompanyRecruitingKnowledgeItem], int]:
        query = select(CompanyRecruitingKnowledgeItem)
        count_query = select(sa_func.count(CompanyRecruitingKnowledgeItem.id))

        query = query.where(CompanyRecruitingKnowledgeItem.org_id == org_id)
        count_query = count_query.where(CompanyRecruitingKnowledgeItem.org_id == org_id)

        if knowledge_type:
            query = query.where(
                CompanyRecruitingKnowledgeItem.knowledge_type == KnowledgeItemType(knowledge_type)
            )
            count_query = count_query.where(
                CompanyRecruitingKnowledgeItem.knowledge_type == KnowledgeItemType(knowledge_type)
            )
        if status:
            query = query.where(
                CompanyRecruitingKnowledgeItem.status == KnowledgeItemStatus(status)
            )
            count_query = count_query.where(
                CompanyRecruitingKnowledgeItem.status == KnowledgeItemStatus(status)
            )
        if job_profile_id:
            query = query.where(
                CompanyRecruitingKnowledgeItem.job_profile_id == job_profile_id
            )
            count_query = count_query.where(
                CompanyRecruitingKnowledgeItem.job_profile_id == job_profile_id
            )

        if only_active:
            today = _today()
            query = query.where(
                CompanyRecruitingKnowledgeItem.status == KnowledgeItemStatus.ACTIVE,
                or_(
                    CompanyRecruitingKnowledgeItem.effective_from.is_(None),
                    CompanyRecruitingKnowledgeItem.effective_from <= today,
                ),
                or_(
                    CompanyRecruitingKnowledgeItem.effective_to.is_(None),
                    CompanyRecruitingKnowledgeItem.effective_to >= today,
                ),
            )
            count_query = count_query.where(
                CompanyRecruitingKnowledgeItem.status == KnowledgeItemStatus.ACTIVE,
                or_(
                    CompanyRecruitingKnowledgeItem.effective_from.is_(None),
                    CompanyRecruitingKnowledgeItem.effective_from <= today,
                ),
                or_(
                    CompanyRecruitingKnowledgeItem.effective_to.is_(None),
                    CompanyRecruitingKnowledgeItem.effective_to >= today,
                ),
            )

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(CompanyRecruitingKnowledgeItem.updated_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_active_for_ai(
        self, org_id: str,
    ) -> list[CompanyRecruitingKnowledgeItem]:
        """AI 可用知识：仅 active + 生效期内。"""
        today = _today()
        result = await self.db.execute(
            select(CompanyRecruitingKnowledgeItem)
            .where(
                CompanyRecruitingKnowledgeItem.org_id == org_id,
                CompanyRecruitingKnowledgeItem.status == KnowledgeItemStatus.ACTIVE,
                or_(
                    CompanyRecruitingKnowledgeItem.effective_from.is_(None),
                    CompanyRecruitingKnowledgeItem.effective_from <= today,
                ),
                or_(
                    CompanyRecruitingKnowledgeItem.effective_to.is_(None),
                    CompanyRecruitingKnowledgeItem.effective_to >= today,
                ),
            )
            .order_by(CompanyRecruitingKnowledgeItem.updated_at.desc())
        )
        return list(result.scalars().all())

    # ── 状态管理 ─────────────────────────────────────────────────────

    async def activate(self, item_id: str, reviewed_by: str) -> CompanyRecruitingKnowledgeItem | None:
        """人工确认：proposed/draft → active。"""
        item = await self.get(item_id)
        if item is None:
            return None
        self._validate_status_transition(item.status, KnowledgeItemStatus.ACTIVE)
        item.status = KnowledgeItemStatus.ACTIVE
        item.reviewed_by = reviewed_by
        item.reviewed_at = _now()
        await self._sync_embedding(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def expire_old_items(self) -> int:
        """自动过期：将 effective_to < today 的 active 条目标记为 expired。"""
        today = _today()
        result = await self.db.execute(
            select(CompanyRecruitingKnowledgeItem)
            .where(
                CompanyRecruitingKnowledgeItem.status == KnowledgeItemStatus.ACTIVE,
                CompanyRecruitingKnowledgeItem.effective_to.is_not(None),
                CompanyRecruitingKnowledgeItem.effective_to < today,
            )
        )
        expired = list(result.scalars().all())
        for item in expired:
            item.status = KnowledgeItemStatus.EXPIRED
            if item.embedding_id:
                await self._remove_embedding(item.embedding_id)
                item.embedding_id = None
        await self.db.commit()
        return len(expired)

    # ── Embedding 同步 ───────────────────────────────────────────────

    async def _sync_embedding(self, item: CompanyRecruitingKnowledgeItem) -> None:
        """生成 embedding 并同步到 Qdrant。"""
        try:
            qdrant_client = await self.qdrant
        except Exception as e:
            logger.warning("Qdrant unavailable for embedding sync: %s", e)
            return

        # 构建文本（标题 + 内容 + 标签）
        text = f"{item.title}\n\n{item.content}"
        if item.tags:
            text += f"\n\n标签: {' '.join(item.tags)}"

        try:
            vector = await self.llm.embed(text)
        except Exception as e:
            logger.warning("LLM embed failed for %s: %s", item.id, e)
            return

        # 确保 collection 存在
        try:
            from qdrant_client.models import VectorParams, Distance
            collections = await qdrant_client.get_collections()
            exists = any(
                c.name == KNOWLEDGE_QDRANT_COLLECTION
                for c in collections.collections
            )
            if not exists:
                await qdrant_client.create_collection(
                    collection_name=KNOWLEDGE_QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
                )
        except Exception as e:
            logger.warning("Qdrant collection check failed: %s", e)
            return

        # 更新或创建 embedding
        point_id = item.embedding_id or str(uuid.uuid4())
        try:
            from qdrant_client.models import PointStruct
            await qdrant_client.upsert(
                collection_name=KNOWLEDGE_QDRANT_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "knowledge_item_id": item.id,
                            "org_id": item.org_id,
                            "title": item.title,
                            "content": item.content,
                            "knowledge_type": item.knowledge_type.value,
                            "tags": item.tags,
                            "source": item.source,
                        },
                    )
                ],
            )
            item.embedding_id = point_id
            await self.db.flush()
        except Exception as e:
            logger.warning("Qdrant upsert failed for %s: %s", item.id, e)

    async def _remove_embedding(self, embedding_id: str) -> None:
        """从 Qdrant 删除 embedding。"""
        try:
            qdrant_client = await self.qdrant
            await qdrant_client.delete(
                collection_name=KNOWLEDGE_QDRANT_COLLECTION,
                points_selector=type("filter", (), {"filter": {"must": [{"has_id": [embedding_id]}]}})(),
            )
        except Exception as e:
            logger.warning("Qdrant delete failed for %s: %s", embedding_id, e)

    # ── 验证 ─────────────────────────────────────────────────────────

    @staticmethod
    def _validate_status_transition(
        current: KnowledgeItemStatus, target: KnowledgeItemStatus,
    ) -> None:
        transitions = {
            KnowledgeItemStatus.DRAFT: {KnowledgeItemStatus.PROPOSED, KnowledgeItemStatus.ARCHIVED},
            KnowledgeItemStatus.PROPOSED: {KnowledgeItemStatus.ACTIVE, KnowledgeItemStatus.DRAFT, KnowledgeItemStatus.ARCHIVED},
            KnowledgeItemStatus.ACTIVE: {KnowledgeItemStatus.EXPIRED, KnowledgeItemStatus.ARCHIVED},
            KnowledgeItemStatus.EXPIRED: {KnowledgeItemStatus.ACTIVE, KnowledgeItemStatus.ARCHIVED},
            KnowledgeItemStatus.ARCHIVED: set(),
        }
        allowed = transitions.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"状态不允许从 {current.value} 转为 {target.value}。"
                f"允许的转换: {[s.value for s in allowed]}"
            )
