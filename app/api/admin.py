"""
Admin API endpoints — document management and system administration.
"""
import logging
import shutil
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.models import User, IngestResponse, DocumentInfo
from app.api.deps import get_current_user
from app.ingestion.pipeline import run_ingestion
from app.ingestion.indexer import get_qdrant_client
from app.rbac.access_control import DEMO_USERS
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Only c_level users can access admin endpoints."""
    if user.role != "c_level":
        raise HTTPException(
            status_code=403,
            detail="Admin access requires c_level role",
        )
    return user


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingestion(
    user: User = Depends(require_admin),
):
    """
    Trigger document re-indexing.

    Scans the data directory, processes all documents, and indexes into Qdrant.
    Requires c_level role.
    """
    logger.info(f"Ingestion triggered by admin: {user.username}")

    try:

        result = run_ingestion()
        return result
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        return IngestResponse(
            status="error",
            message=f"Ingestion failed: {str(e)}",
        )


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(
    user: User = Depends(require_admin),
):
    """List all indexed documents with chunk counts."""
    settings = get_settings()

    try:
        client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION_NAME

        # Check if collection exists
        collections = [c.name for c in client.get_collections().collections]
        if collection_name not in collections:
            return []

        # Scroll through all points to aggregate by document
        doc_stats: dict[str, dict] = {}
        offset = None
        batch_size = 100

        while True:
            results, next_offset = client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=["source_document", "collection"],
            )

            for point in results:
                doc_name = point.payload.get("source_document", "unknown")
                collection = point.payload.get("collection", "unknown")

                if doc_name not in doc_stats:
                    doc_stats[doc_name] = {
                        "filename": doc_name,
                        "collection": collection,
                        "chunk_count": 0,
                    }
                doc_stats[doc_name]["chunk_count"] += 1

            if next_offset is None:
                break
            offset = next_offset

        return [DocumentInfo(**stats) for stats in doc_stats.values()]

    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        return []


@router.delete("/documents/{filename}")
async def delete_document(
    filename: str,
    user: User = Depends(require_admin),
):
    """Delete all chunks for a specific document."""
    settings = get_settings()

    try:
        client = get_qdrant_client()
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client.delete(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source_document",
                        match=MatchValue(value=filename),
                    )
                ]
            ),
        )

        logger.info(f"Deleted document '{filename}' from index")
        return {"status": "success", "message": f"Deleted chunks for '{filename}'"}

    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import UserDB
from app.api.deps import get_password_hash
from app.models import UserCreate

@router.get("/users")
async def list_users(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
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
            "created_at": u.created_at
        }
        for u in db_users
    ]

@router.post("/users", response_model=User)
async def create_user(
    new_user: UserCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new user with a specified role."""
    # Check if username exists
    username = new_user.username.lower().strip()
    result = await db.execute(select(UserDB).where(UserDB.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already registered")

    db_user = UserDB(
        username=username,
        hashed_password=get_password_hash(new_user.password),
        role=new_user.role,
        display_name=new_user.display_name
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    logger.info(f"Admin '{user.username}' created new user '{username}' with role '{new_user.role}'")

    return User(
        username=db_user.username,
        role=db_user.role,
        display_name=db_user.display_name
    )


from pydantic import BaseModel as PydanticBase

class RoleUpdate(PydanticBase):
    role: str

VALID_ROLES = {"employee", "finance", "engineering", "marketing", "c_level"}

@router.patch("/users/{username}/role", response_model=User)
async def update_user_role(
    username: str,
    payload: RoleUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update the role of an existing user. Admin only."""
    if payload.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{payload.role}'. Must be one of: {', '.join(VALID_ROLES)}"
        )

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


class ExtraRolesUpdate(PydanticBase):
    extra_roles: list[str]

@router.patch("/users/{username}/extra-roles")
async def update_user_extra_roles(
    username: str,
    payload: ExtraRolesUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replace the extra access roles for a user. Admin only.
    
    extra_roles is stored as comma-separated string internally.
    Each entry must be a valid role key.
    """
    invalid = [r for r in payload.extra_roles if r not in VALID_ROLES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role(s): {', '.join(invalid)}. Must be from: {', '.join(VALID_ROLES)}"
        )

    result = await db.execute(select(UserDB).where(UserDB.username == username.lower()))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Exclude the user's own primary role from extra_roles to avoid duplication
    cleaned = [r for r in payload.extra_roles if r != db_user.role]
    db_user.extra_roles = ",".join(cleaned)
    await db.commit()
    await db.refresh(db_user)

    logger.info(
        f"Admin '{admin.username}' updated extra roles for '{username}': {cleaned}"
    )

    return {
        "username": db_user.username,
        "role": db_user.role,
        "extra_roles": cleaned,
    }

@router.delete("/users/{username}")
async def delete_user(
    username: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user from the system. Admin only."""
    username = username.lower().strip()
    
    # Prevent admin from deleting themselves
    if username == admin.username.lower().strip():
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
    
    result = await db.execute(select(UserDB).where(UserDB.username == username))
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    await db.delete(db_user)
    await db.commit()
    
    logger.info(f"Admin '{admin.username}' deleted user '{username}'")
    return {"status": "success", "message": f"User '{username}' has been deleted."}


@router.post("/upload", response_class=JSONResponse)
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form(...),
    user: User = Depends(get_current_user)
):
    """
    Upload a document and trigger ingestion.
    Admin only.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    settings = get_settings()
    
    # Map collection to subfolder
    subfolders = ["general", "finance", "engineering", "marketing", "hr"]
    if collection not in subfolders:
        raise HTTPException(status_code=400, detail=f"Invalid collection. Must be one of: {subfolders}")

    # Ensure target directory exists
    target_dir = Path(settings.DATA_DIR) / collection
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / file.filename
    
    logger.info(f"Uploading file: {file.filename} to {collection}")

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Trigger ingestion
    try:
        # We run the full ingestion for simplicity, 
        # but in a production app we might just process the new file.
        result = run_ingestion()
        return {
            "status": "success", 
            "message": f"File '{file.filename}' uploaded and indexed successfully.",
            "ingestion_result": result
        }
    except Exception as e:
        logger.error(f"Ingestion failed after upload: {e}")
        return {
            "status": "partial_success",
            "message": f"File '{file.filename}' uploaded, but indexing failed: {str(e)}"
        }
