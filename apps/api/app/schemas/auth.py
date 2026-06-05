from datetime import datetime

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MembershipInfo(BaseModel):
    org_id: str
    org_name: str
    org_slug: str
    org_plan: str
    role: str
    joined_at: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    memberships: list[MembershipInfo] = []

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None
