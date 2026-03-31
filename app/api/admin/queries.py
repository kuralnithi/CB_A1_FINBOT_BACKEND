"""
Admin API — Query log management endpoints.

Provides read/delete access to the audit log of user queries.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import QueryLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin — Queries"])


# ─── Dependencies ─────────────────────────────────────────────────────────────


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "c_level":
        raise HTTPException(status_code=403, detail="Admin access requires c_level role")
    return user


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/queries")
async def list_queries(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List the most recent 50 queries from the audit log."""
    try:
        result = await db.execute(
            select(QueryLog).order_by(QueryLog.created_at.desc()).limit(50)
        )
        queries = result.scalars().all()
        return [
            {
                "id": q.id,
                "username": q.username,
                "query": q.query,
                "answer": q.answer,
                "user_role": q.user_role,
                "routing_selected": q.routing_selected,
                "is_exported": q.is_exported,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in queries
        ]
    except Exception as e:
        logger.error(f"Failed to fetch queries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch queries")


@router.delete("/queries/{query_id}")
async def delete_query_log(
    query_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific query log entry."""
    try:
        await db.execute(delete(QueryLog).where(QueryLog.id == query_id))
        await db.commit()
        logger.info(f"Admin '{user.username}' deleted query log {query_id}")
        return {"status": "success", "message": f"Query log {query_id} deleted."}
    except Exception as e:
        logger.error(f"Failed to delete query log {query_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete query log")
