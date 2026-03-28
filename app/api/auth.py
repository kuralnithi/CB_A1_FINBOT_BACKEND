"""
Authentication API endpoints.
"""
import logging
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import LoginRequest, TokenResponse, User
from app.api.deps import create_access_token, get_password_hash, verify_password
from app.db.session import get_db
from app.db.models import UserDB
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/setup-admin", response_model=User)
async def setup_admin(db: AsyncSession = Depends(get_db)):
    """
    Initial bootstrap endpoint to create the first admin user.
    Fails if any user already exists.
    """
    settings = get_settings()
    result = await db.execute(select(UserDB).limit(1))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin user already exists or database is not empty."
        )

    # Use default values from settings
    admin_user = UserDB(
        username=settings.ADMIN_USER,
        hashed_password=get_password_hash(settings.ADMIN_PASS),
        role="c_level",
        display_name="System Administrator"
    )
    db.add(admin_user)
    await db.commit()
    await db.refresh(admin_user)
    
    logger.info(f"Initial setup: Admin user '{admin_user.username}' created.")
    
    return User(
        username=admin_user.username,
        role=admin_user.role,
        display_name=admin_user.display_name
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Login with username and password.
    """
    username = request.username.lower().strip()

    result = await db.execute(select(UserDB).where(UserDB.username == username))
    db_user = result.scalar_one_or_none()

    if not db_user or not verify_password(request.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(username=username, role=db_user.role)

    logger.info(f"User logged in: {username} (role={db_user.role})")

    return TokenResponse(
        access_token=token,
        user=User(
            username=db_user.username,
            role=db_user.role,
            display_name=db_user.display_name
        ),
    )


@router.get("/me", response_model=User)
async def get_me(user: User = ...):
    """Get current user info from token."""
    from app.api.deps import get_current_user
    
    # This is handled via dependency injection at the router level
    return user
