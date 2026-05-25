"""知识库 RAG 服务 — 文档嵌入、向量检索、LLM 问答。"""

import hashlib
import logging
import uuid

from app.core.config import settings
from app.core.qdrant import get_qdrant
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

KNOWLEDGE_COLLECTION = "knowledge_base"

# RAG system prompt for Q&A
RAG_QA_SYSTEM_PROMPT = """你是一位知识库 AI 助手，负责根据提供的参考文档回答用户问题。

回答规则:
1. 仅使用下面提供的参考文档内容来回答问题
2. 如果参考文档中没有足够的信息，请明确说明"文档中未找到相关信息"
3. 引用相关内容时，注明来源标题
4. 用中文回答
5. 回答应当结构化、清晰易懂"""


class KnowledgeService:
    """知识库 RAG 服务"""

    def __init__(self):
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    async def ensure_collection(self):
        """确保 Qdrant 集合存在。"""
        try:
            qdrant = await get_qdrant()
            collections = await qdrant.get_collections()
            exists = any(
                c.name == KNOWLEDGE_COLLECTION
                for c in collections.collections
            )
            if not exists:
                from qdrant_client.models import VectorParams, Distance
                await qdrant.create_collection(
                    collection_name=KNOWLEDGE_COLLECTION,
                    vectors_config=VectorParams(
                        size=1024,  # bge-m3 default dimension
                        distance=Distance.COSINE,
                    ),
                )
        except Exception as e:
            # Qdrant 未运行时的降级处理
            logger.warning("Qdrant unavailable: %s", e)

    async def ingest_document(
        self, title: str, content: str, document_id: str | None = None,
    ) -> dict:
        """将文档分块、嵌入并存入 Qdrant。"""
        doc_id = document_id or str(uuid.uuid4())
        chunks = self._chunk_text(content)
        source = title
        tags = []  # Could be passed as param

        try:
            qdrant = await get_qdrant()
            await self.ensure_collection()
        except Exception as e:
            return {
                "document_id": doc_id,
                "title": title,
                "chunks_count": len(chunks),
                "warning": f"Qdrant unavailable, document indexed in memory only: {e}",
            }

        points = []
        for idx, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            try:
                embedding = await self.llm.embed(chunk)
            except Exception as e:
                logger.warning("LLM embed failed for chunk %d: %s", idx, e)
                continue
            points.append({
                "id": chunk_id,
                "vector": embedding,
                "payload": {
                    "document_id": doc_id,
                    "title": title,
                    "content": chunk,
                    "chunk_index": idx,
                    "source": source,
                    "tags": tags,
                },
            })

        if points:
            from qdrant_client.models import PointStruct
            point_objects = [
                PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                for p in points
            ]
            await qdrant.upsert(
                collection_name=KNOWLEDGE_COLLECTION,
                points=point_objects,
            )

        return {
            "document_id": doc_id,
            "title": title,
            "chunks_count": len(chunks),
        }

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """向量检索最相关的文档片段。"""
        try:
            qdrant = await get_qdrant()
            await self.ensure_collection()
        except Exception as e:
            return [{"error": f"Qdrant unavailable: {e}"}]

        try:
            query_vector = await self.llm.embed(query)
        except Exception as e:
            logger.warning("LLM embed failed for search: %s", e)
            return []

        response = await qdrant.query_points(
            collection_name=KNOWLEDGE_COLLECTION,
            query=query_vector,
            limit=top_k,
        )

        return [
            {
                "id": r.id,
                "title": r.payload.get("title", ""),
                "content": r.payload.get("content", ""),
                "score": r.score,
            }
            for r in response.points
            if r.score > 0.3  # relevance threshold
        ]

    async def query(self, query: str, top_k: int = 5) -> dict:
        """RAG 问答：检索 → 生成回答。"""
        sources = await self.search(query, top_k=top_k)

        if not sources or "error" in sources[0]:
            answer = "知识库检索失败，请检查 Qdrant 是否正常运行。"
            return {"answer": answer, "sources": sources}

        if not sources:
            return {
                "answer": "文档中未找到相关信息。",
                "sources": [],
            }

        context_parts = []
        for s in sources:
            context_parts.append(f"[来源: {s['title']}]\n{s['content']}")

        context = "\n\n---\n\n".join(context_parts)

        messages = [
            {"role": "system", "content": RAG_QA_SYSTEM_PROMPT},
            {"role": "user", "content": f"参考文档:\n{context}\n\n---\n\n用户问题: {query}"},
        ]

        try:
            answer = await self.llm.chat(messages, temperature=0.3, max_tokens=1024)
        except Exception as e:
            logger.warning("LLM chat failed for RAG query: %s", e)
            return {
                "answer": "AI 回答不可用，请稍后重试。",
                "sources": sources,
            }

        return {
            "answer": answer.strip(),
            "sources": sources,
        }

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
        """将文本切分为重叠块。"""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end >= len(text):
                chunks.append(text[start:])
                break

            # 尽量在段落或句子边界处切割
            split_at = text.rfind("\n\n", start, end)
            if split_at == -1 or split_at <= start:
                split_at = text.rfind(". ", start, end)
            if split_at == -1 or split_at <= start:
                split_at = end

            chunks.append(text[start:split_at].strip())
            start = split_at - overlap

        return [c for c in chunks if c]
