from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)


class UserService:
    @staticmethod
    async def register(
        db: AsyncSession, data: RegisterRequest
    ) -> tuple[User, TokenResponse]:
        existing = await UserService.get_by_email(db, data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            name=data.name,
            role=UserRole.HR,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        token = create_access_token(user.id, user.role.value)
        return user, TokenResponse(access_token=token)

    @staticmethod
    async def login(
        db: AsyncSession, data: LoginRequest
    ) -> tuple[User, TokenResponse]:
        user = await UserService.get_by_email(db, data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )

        token = create_access_token(user.id, user.role.value)
        return user, TokenResponse(access_token=token)

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: str) -> User:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    @staticmethod
    def to_response(user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
        )
