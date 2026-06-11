from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlatformConfigResponse(BaseModel):
    name: str
    display_name: str
    category: str
    anti_crawl_level: int
    requires_login: bool
    rate_limit: int
    daily_quota_per_account: int
    enabled: bool
    health_status: str
    health_checked_at: datetime | None
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlatformConfigUpdate(BaseModel):
    enabled: bool | None = None
    rate_limit: int | None = Field(default=None, ge=1, le=3600)
    daily_quota_per_account: int | None = Field(default=None, ge=1)
    config: dict[str, Any] | None = None


class AccountCreate(BaseModel):
    display_name: str = Field(..., max_length=100)
    account_type: str = Field(default="crawl", pattern="^(primary|backup|crawl)$")
    encrypted_cookies: str | None = None
    cookie_expires_at: datetime | None = None


class AccountResponse(BaseModel):
    id: str
    platform: str
    display_name: str
    account_type: str
    is_active: bool
    status: str
    daily_used: int
    consecutive_failures: int
    last_banned_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
