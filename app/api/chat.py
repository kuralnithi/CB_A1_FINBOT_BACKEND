import logging
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatRequest, ChatResponse, User
from app.api.deps import get_current_user
from app.services.rag_service import process_query
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
    Streaming compatibility endpoint using the main rag_service.
    """
    logger.info(f"Streaming request: user={user.username}, query='{request.query[:50]}...'")
    
    async def stream_generator():
        try:
            # First notify that we are generating
            yield f"data: {json.dumps({'status': 'Analyzing and retrieving documents...'})}\n\n"
            
            response = await process_query(request.query, user, request.session_id)
            
            if response.blocked:
                yield f"data: {json.dumps({'error': response.blocked_reason, 'blocked': True, 'reason': getattr(response, 'blocked_reason', 'blocked')})}\n\n"
            else:
                # Provide the tokens
                if response.answer:
                    # In a real streaming scenario we would stream tokens. Here we send the whole response as one chunk.
                    yield f"data: {json.dumps({'token': response.answer})}\n\n"
                
                # Provide sources and warnings if present
                # To attach it to the final event so frontend can pick it up
                done_payload = {
                    'done': True, 
                    'accessible_collections': response.accessible_collections,
                    'sources': [source.dict() for source in response.sources] if getattr(response, "sources", None) else [],
                    'guardrail_warnings': [w.dict() for w in response.guardrail_warnings] if getattr(response, "guardrail_warnings", None) else []
                }
                yield f"data: {json.dumps(done_payload)}\n\n"
                
        except Exception as e:
            logger.error(f"Stream endpoint failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': f'System Error: {str(e)[:100]}...', 'blocked': True})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream"
    )
