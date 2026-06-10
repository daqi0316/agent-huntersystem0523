from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_profile import (
    JobProfile,
    JobProfileDimension,
    JobProfileRequirementItem,
    JobProfileRequirementType,
    JobProfileVersion,
    JobProfileVersionStatus,
)
from app.schemas.job_profile import JobProfileCreate, JobProfileUpdate, JobProfileVersionCreate


class JobProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        level: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[JobProfile], int]:
        query = select(JobProfile)
        count_query = select(func.count(JobProfile.id))

        if search:
            pattern = f"%{search}%"
            condition = or_(
                JobProfile.code.ilike(pattern),
                JobProfile.title.ilike(pattern),
                JobProfile.department.ilike(pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)
        if level:
            query = query.where(JobProfile.level == level)
            count_query = count_query.where(JobProfile.level == level)
        if is_active is not None:
            query = query.where(JobProfile.is_active == is_active)
            count_query = count_query.where(JobProfile.is_active == is_active)

        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(JobProfile.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_by_id(self, profile_id: str) -> JobProfile | None:
        try:
            uuid.UUID(profile_id)
        except (ValueError, AttributeError):
            return None
        result = await self.db.execute(select(JobProfile).where(JobProfile.id == profile_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> JobProfile | None:
        result = await self.db.execute(select(JobProfile).where(JobProfile.code == code))
        return result.scalar_one_or_none()

    async def create(self, data: JobProfileCreate) -> JobProfile:
        profile = JobProfile(**data.model_dump(mode="json"))
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def create_version(
        self,
        profile_id: str,
        data: JobProfileVersionCreate,
        created_by: str,
    ) -> JobProfileVersion | None:
        from datetime import datetime, timezone

        profile = await self.get_by_id(profile_id)
        if profile is None:
            return None
        result = await self.db.execute(
            select(func.max(JobProfileVersion.version)).where(JobProfileVersion.job_profile_id == profile_id)
        )
        next_version = (result.scalar() or 0) + 1
        status = JobProfileVersionStatus(data.status)
        now = datetime.now(timezone.utc)
        if status == JobProfileVersionStatus.ACTIVE:
            now = datetime.now(timezone.utc)
            await self.db.execute(
                update(JobProfileVersion)
                .where(
                    JobProfileVersion.job_profile_id == profile_id,
                    JobProfileVersion.status == JobProfileVersionStatus.ACTIVE,
                )
                .values(status=JobProfileVersionStatus.ARCHIVED, archived_at=now)
            )
        version = JobProfileVersion(
            id=str(uuid.uuid4()),
            job_profile_id=profile.id,
            version=next_version,
            status=status,
            change_reason=data.change_reason,
            snapshot=self._snapshot(profile),
            created_by=created_by,
            activated_by=created_by if status == JobProfileVersionStatus.ACTIVE else None,
            activated_at=now if status == JobProfileVersionStatus.ACTIVE else None,
            effective_from=now if status == JobProfileVersionStatus.ACTIVE else None,
        )
        self.db.add(version)
        await self.db.flush()
        for index, label in enumerate(profile.hard_requirements or []):
            self.db.add(self._requirement(version.id, JobProfileRequirementType.HARD, label, index))
        for index, label in enumerate(profile.soft_requirements or []):
            self.db.add(self._requirement(version.id, JobProfileRequirementType.SOFT, label, index))
        for index, item in enumerate(profile.evaluation_dimensions or []):
            self.db.add(
                JobProfileDimension(
                    id=str(uuid.uuid4()),
                    profile_version_id=version.id,
                    name=item.get("dimension") or f"维度{index + 1}",
                    category=None,
                    weight=item.get("weight") or 0,
                    description=item.get("must_have"),
                    must_have=item.get("must_have"),
                    key_questions=item.get("key_questions") or [],
                    red_flags=item.get("red_flags") or [],
                    order_index=index,
                )
            )
        await self.db.commit()
        await self.db.refresh(version)
        # 预加载 relationship，供 version_to_dict 直接使用（避免 N+1）
        await self.db.refresh(version, attribute_names=["requirements", "dimensions"])
        return version

    async def list_versions(self, profile_id: str) -> list[dict]:
        if not self._valid_uuid(profile_id):
            return []
        result = await self.db.execute(
            select(JobProfileVersion)
            .options(selectinload(JobProfileVersion.requirements), selectinload(JobProfileVersion.dimensions))
            .where(JobProfileVersion.job_profile_id == profile_id)
            .order_by(JobProfileVersion.version.desc())
        )
        return [await self.version_to_dict(item) for item in result.scalars().all()]

    async def get_version(self, version_id: str) -> JobProfileVersion | None:
        if not self._valid_uuid(version_id):
            return None
        result = await self.db.execute(select(JobProfileVersion).where(JobProfileVersion.id == version_id))
        return result.scalar_one_or_none()

    async def activate_version(self, profile_id: str, version_id: str, activated_by: str | None = None) -> JobProfileVersion | None:
        from datetime import datetime, timezone

        version = await self.get_version(version_id)
        if version is None or version.job_profile_id != profile_id:
            return None
        await self.db.execute(
            update(JobProfileVersion)
            .where(
                JobProfileVersion.job_profile_id == profile_id,
                JobProfileVersion.status == JobProfileVersionStatus.ACTIVE,
            )
            .values(status=JobProfileVersionStatus.ARCHIVED, archived_at=datetime.now(timezone.utc))
        )
        now = datetime.now(timezone.utc)
        version.status = JobProfileVersionStatus.ACTIVE
        version.activated_by = activated_by
        version.activated_at = now
        version.effective_from = now
        version.archived_at = None
        await self.db.commit()
        await self.db.refresh(version)
        await self.db.refresh(version, attribute_names=["requirements", "dimensions"])
        return version

    async def template_library(self) -> list[dict]:
        items, _ = await self.list(limit=100, is_active=True)
        return [
            {
                "id": item.id,
                "code": item.code,
                "title": item.title,
                "level": item.level,
                "department": item.department,
                "hard_requirement_count": len(item.hard_requirements or []),
                "soft_requirement_count": len(item.soft_requirements or []),
                "dimension_count": len(item.evaluation_dimensions or []),
            }
            for item in items
        ]

    async def version_to_dict(self, version: JobProfileVersion) -> dict:
        reqs = sorted(version.requirements, key=lambda r: (r.type.value, r.order_index))
        dims = sorted(version.dimensions, key=lambda d: d.order_index)
        return {
            "id": version.id,
            "job_profile_id": version.job_profile_id,
            "version": version.version,
            "status": version.status.value,
            "change_reason": version.change_reason,
            "snapshot": version.snapshot,
            "created_by": version.created_by,
            "created_at": version.created_at,
            "effective_from": version.effective_from,
            "effective_to": version.effective_to,
            "activated_by": version.activated_by,
            "activated_at": version.activated_at,
            "archived_at": version.archived_at,
            "requirements": [self._requirement_to_dict(item) for item in reqs],
            "dimensions": [self._dimension_to_dict(item) for item in dims],
        }

    @staticmethod
    def _valid_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    @staticmethod
    def _snapshot(profile: JobProfile) -> dict:
        return {
            "code": profile.code,
            "title": profile.title,
            "level": profile.level,
            "department": profile.department,
            "description": profile.description,
            "hard_requirements": profile.hard_requirements or [],
            "soft_requirements": profile.soft_requirements or [],
            "evaluation_dimensions": profile.evaluation_dimensions or [],
            "salary_band": profile.salary_band or {},
            "interview_focus": profile.interview_focus or [],
        }

    @staticmethod
    def _requirement(
        version_id: str,
        type_: JobProfileRequirementType,
        label: str,
        index: int,
    ) -> JobProfileRequirementItem:
        return JobProfileRequirementItem(
            id=str(uuid.uuid4()),
            profile_version_id=version_id,
            type=type_,
            category=None,
            label=label,
            description=label,
            must_have=type_ == JobProfileRequirementType.HARD,
            weight=None,
            evidence_required=None,
            red_flag_if_missing=type_ == JobProfileRequirementType.HARD,
            order_index=index,
        )

    @staticmethod
    def _requirement_to_dict(item: JobProfileRequirementItem) -> dict:
        return {
            "id": item.id,
            "profile_version_id": item.profile_version_id,
            "type": item.type.value,
            "category": item.category,
            "label": item.label,
            "description": item.description,
            "must_have": item.must_have,
            "weight": item.weight,
            "evidence_required": item.evidence_required,
            "red_flag_if_missing": item.red_flag_if_missing,
            "order_index": item.order_index,
        }

    @staticmethod
    def _dimension_to_dict(item: JobProfileDimension) -> dict:
        return {
            "id": item.id,
            "profile_version_id": item.profile_version_id,
            "name": item.name,
            "category": item.category,
            "weight": item.weight,
            "description": item.description,
            "must_have": item.must_have,
            "key_questions": item.key_questions or [],
            "red_flags": item.red_flags or [],
            "order_index": item.order_index,
        }

    async def update(self, profile_id: str, data: JobProfileUpdate) -> JobProfile | None:
        profile = await self.get_by_id(profile_id)
        if profile is None:
            return None
        for key, value in data.model_dump(exclude_unset=True, mode="json").items():
            setattr(profile, key, value)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile
