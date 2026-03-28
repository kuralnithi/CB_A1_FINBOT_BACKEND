"""
RBAC-aware retriever — queries Qdrant with pre-applied filters.

CRITICAL: RBAC filtering happens at the Qdrant query level.
Unauthorized chunks are NEVER retrieved.
"""
import logging
import anyio
from sentence_transformers import SentenceTransformer

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter

from app.config import get_settings
from app.ingestion.indexer import get_embedding_model, get_async_qdrant_client
from app.rbac.access_control import build_qdrant_filter
from app.models import SourceCitation

logger = logging.getLogger(__name__)


async def retrieve_chunks(
    query: str,
    role: str,
    target_collections: list[str] | None = None,
    extra_roles: list[str] | None = None,
    top_k: int = 5,
) -> tuple[list[dict], list[SourceCitation]]:
    """
    Retrieve chunks from Qdrant with RBAC filter applied AT QUERY LEVEL.
    Async implementation for production efficiency.
    """
    settings = get_settings()
    model = get_embedding_model()
    # Use AsyncQdrantClient
    client = get_async_qdrant_client()

    # Generate query embedding — run in thread pool as it's CPU intensive
    logger.debug(f"Generating embedding for query: '{query[:50]}...'")
    try:
        query_vector = await anyio.to_thread.run_sync(
            lambda: model.encode(query, normalize_embeddings=True).tolist()
        )
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}", exc_info=True)
        return [], []

    # Build RBAC-aware filter
    extra_roles = extra_roles or []
    qdrant_filter = build_qdrant_filter(role, target_collections, extra_roles)

    logger.info(
        f"Retrieving chunks: role='{role}', extra={extra_roles}, "
        f"collections={target_collections}, top_k={top_k}"
    )

    # Query Qdrant with filter asynchronously
    try:
        results = await client.search(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
    except Exception as e:
        logger.error(f"Qdrant search failed: {e}", exc_info=True)
        return [], []
    finally:
        # Note: In a real production app, you might want to reuse the client 
        # but here we close it to be safe if it's created per request
        await client.close()

    chunks = []
    citations = []

    for result in results:
        payload = result.payload or {}
        chunks.append({
            "text": payload.get("text", ""),
            "source_document": payload.get("source_document", ""),
            "collection": payload.get("collection", ""),
            "section_title": payload.get("section_title", ""),
            "page_number": payload.get("page_number", 0),
            "chunk_type": payload.get("chunk_type", "text"),
            "parent_summary": payload.get("parent_summary", ""),
            "score": result.score,
        })

        citations.append(SourceCitation(
            document=payload.get("source_document", "unknown"),
            page_number=payload.get("page_number", 0),
            section=payload.get("section_title", ""),
            chunk_type=payload.get("chunk_type", "text"),
            relevance_score=round(result.score, 4),
        ))

    logger.info(f"Retrieved {len(chunks)} chunks for role '{role}'")
    return chunks, citations
