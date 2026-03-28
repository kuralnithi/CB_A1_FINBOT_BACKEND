"""
Authentication dependencies — JWT token creation and verification.
"""
import logging
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings
from app.models import User
from app.db.session import get_db
from app.db.models import UserDB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import bcrypt

logger = logging.getLogger(__name__)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

security = HTTPBearer()


def create_access_token(username: str, role: str) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    FastAPI dependency — extract and verify user from JWT token and DB.

    Raises HTTPException 401 if token is invalid, expired, or user not found.
    """
    settings = get_settings()
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")

        if username is None or role is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    # Look up user in the actual database
    result = await db.execute(select(UserDB).where(UserDB.username == username))
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise credentials_exception

    return User(
        username=db_user.username,
        role=db_user.role,
        display_name=db_user.display_name,
        extra_roles=[r for r in (db_user.extra_roles or "").split(",") if r],
    )
