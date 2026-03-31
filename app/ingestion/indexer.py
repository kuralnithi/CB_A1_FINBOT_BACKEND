"""
Vector store indexer — generates embeddings and upserts into Qdrant.

Uses HuggingFace BGE embeddings and Qdrant for storage.
"""
import logging
import uuid
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)
from sentence_transformers import SentenceTransformer

from app.config import get_settings
from app.models import ChunkMetadata

logger = logging.getLogger(__name__)

# Module-level cache for the embedding model
_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Get or create the embedding model (cached)."""
    global _embedding_model
    if _embedding_model is None:
        settings = get_settings()
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL_NAME}")
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _embedding_model


def get_qdrant_client() -> QdrantClient:
    """Create a Qdrant client (works for both local and cloud)."""
    settings = get_settings()
    if settings.qdrant_is_cloud:
        return QdrantClient(url=settings.QDRANT_HOST, api_key=settings.QDRANT_API_KEY or None)
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def get_async_qdrant_client() -> AsyncQdrantClient:
    """Create an asynchronous Qdrant client (works for both local and cloud)."""
    settings = get_settings()
    if settings.qdrant_is_cloud:
        return AsyncQdrantClient(url=settings.QDRANT_HOST, api_key=settings.QDRANT_API_KEY or None)
    return AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def ensure_collection_exists(client: QdrantClient, collection_name: str, vector_size: int = 384):
    """Create Qdrant collection if it doesn't exist."""
    collections = [c.name for c in client.get_collections().collections]

    if collection_name not in collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: {collection_name}")
    else:
        logger.info(f"Qdrant collection already exists: {collection_name}")


def index_chunks(chunks: list[dict]) -> int:
    """
    Generate embeddings and upsert chunks into Qdrant.

    Args:
        chunks: List of dicts with 'text' and 'metadata' (ChunkMetadata)

    Returns:
        Number of chunks indexed
    """
    if not chunks:
        return 0

    settings = get_settings()
    model = get_embedding_model()
    client = get_qdrant_client()

    # Ensure collection exists
    ensure_collection_exists(client, settings.QDRANT_COLLECTION_NAME, vector_size=384)

    # Generate embeddings in batches
    texts = [c["text"] for c in chunks]
    batch_size = 64
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_embeddings.extend(embeddings.tolist())
        logger.info(f"Embedded batch {i // batch_size + 1}/{(len(texts) + batch_size - 1) // batch_size}")

    # Build Qdrant points
    points = []
    for chunk, embedding in zip(chunks, all_embeddings):
        meta: ChunkMetadata = chunk["metadata"]
        point_id = str(uuid.uuid4())

        payload = {
            "text": chunk["text"],
            "chunk_id": meta.chunk_id,
            "source_document": meta.source_document,
            "collection": meta.collection,
            "access_roles": meta.access_roles,
            "section_title": meta.section_title,
            "page_number": meta.page_number,
            "chunk_type": meta.chunk_type,
            "parent_chunk_id": meta.parent_chunk_id or "",
            "hierarchy_path": meta.hierarchy_path,
            "parent_summary": meta.parent_summary,
        }

        points.append(PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload,
        ))

    # Upsert in batches
    upsert_batch_size = 100
    for i in range(0, len(points), upsert_batch_size):
        batch = points[i:i + upsert_batch_size]
        client.upsert(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points=batch,
        )
        logger.info(f"Upserted batch {i // upsert_batch_size + 1}/{(len(points) + upsert_batch_size - 1) // upsert_batch_size}")

    logger.info(f"Indexed {len(points)} chunks into Qdrant collection '{settings.QDRANT_COLLECTION_NAME}'")
    return len(points)
