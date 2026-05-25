from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token

security_scheme = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str:
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return user_id


async def get_optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str | None:
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    return payload.get("sub")


__all__ = ["get_db", "get_current_user_id", "get_optional_user_id"]
