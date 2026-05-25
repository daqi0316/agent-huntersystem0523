"""知识库 Pydantic schemas — RAG 问答。"""

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentUploadRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500, description="文档标题")
    content: str = Field(..., min_length=1, description="文档内容（支持 Markdown）")
    source: str | None = Field("manual", description="来源（manual/upload/import）")
    tags: list[str] = Field(default_factory=list, description="标签列表")


class DocumentRead(BaseModel):
    id: str
    title: str
    source: str
    tags: list[str]
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="用户提问")
    top_k: int = Field(5, ge=1, le=20, description="检索匹配数量")


class KnowledgeSearchResult(BaseModel):
    id: str
    title: str
    content: str
    score: float


class KnowledgeQueryResponse(BaseModel):
    success: bool = True
    answer: str = ""
    sources: list[KnowledgeSearchResult] = []


class DocumentIngestResponse(BaseModel):
    success: bool = True
    document_id: str = ""
    title: str = ""
    chunks_count: int = 0
