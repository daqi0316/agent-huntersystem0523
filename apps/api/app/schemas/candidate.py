from datetime import datetime

from pydantic import BaseModel, EmailStr


class CandidateCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    summary: str | None = None
    skills: list[str] = []
    experience_years: int | None = None
    education: str | None = None
    current_company: str | None = None
    current_title: str | None = None


class CandidateUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    summary: str | None = None
    skills: list[str] | None = None
    experience_years: int | None = None
    education: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    status: str | None = None


class CandidateRead(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None = None
    summary: str | None = None
    skills: list[str] = []
    experience_years: int | None = None
    education: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
