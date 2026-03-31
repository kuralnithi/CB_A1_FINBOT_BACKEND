"""
Admin API — User management endpoints.

Handles user CRUD, role updates, and extra-role assignments.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserCreate
from app.api.deps import get_current_user, get_password_hash
from app.db.session import get_db
from app.db.models import UserDB

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin — Users"])

VALID_ROLES = {"employee", "finance", "engineering", "marketing", "c_level"}


# ─── Dependencies ─────────────────────────────────────────────────────────────


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "c_level":
        raise HTTPException(status_code=403, detail="Admin access requires c_level role")
    return user


# ─── Schemas ──────────────────────────────────────────────────────────────────


class RoleUpdate(BaseModel):
    """Payload for updating a user's primary role."""
    role: str


class ExtraRolesUpdate(BaseModel):
    """Payload for replacing a user's extra access roles."""
    extra_roles: list[str]


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/users")
async def list_users(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users in the system."""
    result = await db.execute(select(UserDB))
    db_users = result.scalars().all()
    return [
        {
            "username": u.username,
            "role": u.role,
            "display_name": u.display_name,
            "extra_roles": [r for r in (u.extra_roles or "").split(",") if r],
            "created_at": u.created_at,
        }
        for u in db_users
    ]


@router.post("/users", response_model=User)
async def create_user(
    new_user: UserCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user with a specified role."""
    username = new_user.username.lower().strip()

    result = await db.execute(select(UserDB).where(UserDB.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already registered")

    db_user = UserDB(
        username=username,
        hashed_password=get_password_hash(new_user.password),
        role=new_user.role,
        display_name=new_user.display_name,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    logger.info(f"Admin '{user.username}' created user '{username}' (role={new_user.role})")
    return User(username=db_user.username, role=db_user.role, display_name=db_user.display_name)


@router.patch("/users/{username}/role", response_model=User)
async def update_user_role(
    username: str,
    payload: RoleUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's primary role."""
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    result = await db.execute(select(UserDB).where(UserDB.username == username.lower()))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = db_user.role
    db_user.role = payload.role
    await db.commit()
    await db.refresh(db_user)

    logger.info(f"Admin '{admin.username}' changed '{username}' role: {old_role} → {payload.role}")
    return User(
        username=db_user.username,
        role=db_user.role,
        display_name=db_user.display_name,
        extra_roles=[r for r in (db_user.extra_roles or "").split(",") if r],
    )


@router.patch("/users/{username}/extra-roles")
async def update_user_extra_roles(
    username: str,
    payload: ExtraRolesUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replace the extra access roles for a user."""
    invalid = [r for r in payload.extra_roles if r not in VALID_ROLES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid role(s): {', '.join(invalid)}")

    result = await db.execute(select(UserDB).where(UserDB.username == username.lower()))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    cleaned = [r for r in payload.extra_roles if r != db_user.role]
    db_user.extra_roles = ",".join(cleaned)
    await db.commit()
    await db.refresh(db_user)

    logger.info(f"Admin '{admin.username}' updated extra roles for '{username}': {cleaned}")
    return {"username": db_user.username, "role": db_user.role, "extra_roles": cleaned}


@router.delete("/users/{username}")
async def delete_user(
    username: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user from the system."""
    username = username.lower().strip()

    if username == admin.username.lower().strip():
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

    result = await db.execute(select(UserDB).where(UserDB.username == username))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(db_user)
    await db.commit()

    logger.info(f"Admin '{admin.username}' deleted user '{username}'")
    return {"status": "success", "message": f"User '{username}' deleted."}
