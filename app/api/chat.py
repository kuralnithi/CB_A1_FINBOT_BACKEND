import logging
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatRequest, ChatResponse, User
from app.api.deps import get_current_user
from app.services.rag_service_2 import process_query, stream_query
from app.db.session import get_db
from app.db.models import QueryLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Legacy non-streaming endpoint. Uses the experimental agent pipeline.
    """
    try:
        response = await process_query(
            query=request.query,
            user=user,
            session_id=request.session_id,
        )
        
        # Log to PostgreSQL
        query_log = QueryLog(
            username=user.username,
            query=request.query,
            answer=response.answer,
            user_role=user.role,
            routing_selected=response.route_selected
        )
        db.add(query_log)
        await db.commit()

        return response
    except Exception as e:
        logger.error(f"Chat endpoint failed: {e}", exc_info=True)
        return ChatResponse(
            answer=f"Error: {str(e)[:100]}",
            blocked=True,
            blocked_reason="system_error",
            user_role=user.role,
        )

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    user: User = Depends(get_current_user)
):
    """
    Production-grade streaming endpoint (SSE).
    Provides real-time tokens and agent status updates.
    """
    logger.info(f"Streaming request: user={user.username}, query='{request.query[:50]}...'")
    
    return StreamingResponse(
        stream_query(request.query, user, request.session_id),
        media_type="text/event-stream"
    )
