"""向量检索 API — 语义搜索 / 文本嵌入。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user_id
from app.llm import get_llm_client
from app.services.knowledge import KnowledgeService

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="搜索查询")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数量")


class SearchResultItem(BaseModel):
    id: str = ""
    title: str = ""
    content: str = ""
    score: float = 0.0


class SearchResponse(BaseModel):
    success: bool = True
    results: list[SearchResultItem] = []


class EmbedRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000, description="待嵌入文本")


class EmbedResponse(BaseModel):
    success: bool = True
    embedding: list[float] = []
    dimension: int = 0


@router.post("/search", response_model=SearchResponse)
async def vector_search(
    req: SearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """向量检索 — 语义搜索知识库。"""
    service = KnowledgeService()
    results = await service.search(query=req.query, top_k=req.top_k)

    items = []
    for r in results:
        if "error" not in r:
            items.append(SearchResultItem(
                id=r.get("id", ""),
                title=r.get("title", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
            ))

    return SearchResponse(results=items)


@router.post("/embed", response_model=EmbedResponse)
async def embed_text(
    req: EmbedRequest,
    user_id: str = Depends(get_current_user_id),
):
    """文本嵌入 — 将文本转为向量。"""
    llm = get_llm_client()
    embedding = await llm.embed(req.text)
    return EmbedResponse(embedding=embedding, dimension=len(embedding))
