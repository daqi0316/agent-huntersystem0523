from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=500, description="搜索关键词")
    platforms: list[str] | None = Field(default=None, description="目标平台列表")
    filters: dict[str, Any] = Field(default_factory=dict, description="筛选条件")
    priority: int = Field(default=50, ge=0, le=100, description="优先级 0-100")
    scheduled_at: datetime | None = Field(default=None, description="定时执行时间")
    org_id: str | None = Field(default=None, description="组织 ID")
    created_by: str | None = Field(default=None, description="创建者")


class TaskResponse(BaseModel):
    id: str
    org_id: str
    created_by: str
    keyword: str
    platforms: list[str] | None
    filters: dict[str, Any]
    status: str
    progress: dict[str, Any]
    total_found: int
    after_dedup: int
    new_this_run: int
    priority: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListParams(BaseModel):
    status: str | None = Field(default=None, description="按状态筛选")
    platform: str | None = Field(default=None, description="按平台筛选")
    keyword: str | None = Field(default=None, description="搜索关键词")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")
    sort_by: str = Field(default="created_at", description="排序字段")
    sort_order: str = Field(default="desc", description="desc/asc")
