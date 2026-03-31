"""
Admin API — Document management endpoints.

Handles document listing, deletion, upload, and re-indexing triggers.
"""
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, IngestResponse, DocumentInfo
from app.api.deps import get_current_user
from app.ingestion.pipeline import run_ingestion
from app.ingestion.status_tracker import get_status
from app.ingestion.indexer import get_qdrant_client
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin — Documents"])


# ─── Dependencies ─────────────────────────────────────────────────────────────


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Only c_level users can access admin endpoints."""
    if user.role != "c_level":
        raise HTTPException(status_code=403, detail="Admin access requires c_level role")
    return user


# ─── Ingestion ────────────────────────────────────────────────────────────────


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingestion(
    background_tasks: BackgroundTasks,
    user: User = Depends(require_admin),
):
    """
    Trigger document re-indexing in the background.

    Scans the data directory, processes all documents, and indexes into Qdrant.
    """
    logger.info(f"Ingestion triggered by admin: {user.username}")
    try:
        background_tasks.add_task(run_ingestion)
        return IngestResponse(
            status="success",
            message="Ingestion started. Check /api/admin/ingest/status for progress.",
        )
    except Exception as e:
        logger.error(f"Ingestion failed to start: {e}", exc_info=True)
        return IngestResponse(status="error", message=f"Ingestion failed: {e}")


@router.get("/ingest/status")
async def get_ingestion_status(user: User = Depends(require_admin)):
    """Get the current progress of background ingestion."""
    return get_status()


# ─── Document CRUD ────────────────────────────────────────────────────────────


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(user: User = Depends(require_admin)):
    """List all indexed documents with chunk counts from Qdrant."""
    settings = get_settings()
    try:
        client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION_NAME

        collections = [c.name for c in client.get_collections().collections]
        if collection_name not in collections:
            return []

        doc_stats: dict[str, dict] = {}
        offset = None

        while True:
            results, next_offset = client.scroll(
                collection_name=collection_name,
                limit=100,
                offset=offset,
                with_payload=["source_document", "collection"],
            )
            for point in results:
                doc_name = point.payload.get("source_document", "unknown")
                collection = point.payload.get("collection", "unknown")
                if doc_name not in doc_stats:
                    doc_stats[doc_name] = {"filename": doc_name, "collection": collection, "chunk_count": 0}
                doc_stats[doc_name]["chunk_count"] += 1

            if next_offset is None:
                break
            offset = next_offset

        return [DocumentInfo(**stats) for stats in doc_stats.values()]
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        return []


@router.delete("/documents/{filename}")
async def delete_document(filename: str, user: User = Depends(require_admin)):
    """Delete all chunks for a specific document from Qdrant."""
    settings = get_settings()
    try:
        client = get_qdrant_client()
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client.delete(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points_selector=Filter(
                must=[FieldCondition(key="source_document", match=MatchValue(value=filename))]
            ),
        )
        logger.info(f"Deleted document '{filename}' from index")
        return {"status": "success", "message": f"Deleted chunks for '{filename}'"}
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Upload ───────────────────────────────────────────────────────────────────


VALID_COLLECTIONS = {"general", "finance", "engineering", "marketing", "hr"}


@router.post("/upload", response_class=JSONResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection: str = Form(...),
    admin: User = Depends(require_admin),
):
    """Upload a document to a collection folder and trigger re-indexing."""
    settings = get_settings()

    if collection not in VALID_COLLECTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid collection. Must be one of: {VALID_COLLECTIONS}")

    try:
        target_dir = Path(settings.DATA_DIR) / collection
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = file.filename.replace(" ", "_")
        file_path = target_dir / filename

        logger.info(f"Uploading file: {filename} → {collection}")
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        background_tasks.add_task(run_ingestion)

        return {"status": "success", "message": f"'{filename}' uploaded to '{collection}'. Ingestion started."}
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
