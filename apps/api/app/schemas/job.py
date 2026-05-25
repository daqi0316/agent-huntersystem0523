from datetime import datetime

from pydantic import BaseModel


class JobCreate(BaseModel):
    title: str
    department: str | None = None
    description: str | None = None
    requirements: str | None = None
    location: str | None = None
    salary_range: str | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    department: str | None = None
    description: str | None = None
    requirements: str | None = None
    location: str | None = None
    salary_range: str | None = None
    status: str | None = None


class JobRead(BaseModel):
    id: str
    title: str
    department: str | None = None
    description: str | None = None
    requirements: str | None = None
    location: str | None = None
    salary_range: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
