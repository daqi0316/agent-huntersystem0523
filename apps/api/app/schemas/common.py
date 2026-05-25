from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Message(BaseModel):
    message: str


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class ListResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T] = []
    items: list[T] = []
    total: int = 0
    skip: int = 0
    limit: int = 20
    meta: PaginationMeta | None = None


class ResponseEnvelope(BaseModel):
    success: bool = True
    data: dict | list | None = None
    error: str | None = None
    meta: PaginationMeta | None = None
