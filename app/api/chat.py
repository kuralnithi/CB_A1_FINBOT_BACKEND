"""
Chat API endpoints — RAG query pipeline.
"""
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.models import ChatRequest, ChatResponse, User
from app.api.deps import get_current_user
from app.services.rag_service import process_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
):
    """
    Process a chat query through the full RAG pipeline.
    Production-grade endpoint with async handling and error safety.
    """
    logger.info(
        f"Chat request: user={user.username}, role={user.role}, "
        f"session={request.session_id}, query='{request.query[:80]}...'"
    )

    try:
        # Await the async process_query
        response = await process_query(
            query=request.query,
            user=user,
            session_id=request.session_id,
        )
        return response
    except Exception as e:
        logger.error(f"Chat endpoint failed [{type(e).__name__}]: {e}", exc_info=True)
        # Return a structured response even on failure
        return ChatResponse(
            answer="I am encountering an unexpected error. Please try again or contact support.",
            blocked=True,
            blocked_reason="system_error",
            user_role=user.role,
        )
