import os
import logging
import sys
import asyncio
from pathlib import Path

# CRITICAL: For Windows compatibility with psycopg3 async mode, 
# this MUST be set if this file is run in a separate process.
if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from app.ingestion.status_tracker import update_status
from app.ingestion.parser import scan_data_directory, preprocess_file
from app.ingestion.chunker import create_chunks
from app.ingestion.summarizer import generate_parent_summaries
from app.ingestion.indexer import index_chunks, get_qdrant_client, ensure_collection_exists
from app.config import get_settings
from app.models import IngestResponse

logger = logging.getLogger(__name__)


def run_ingestion(data_dir: str | None = None) -> IngestResponse:
    """
    Run the full ingestion pipeline.

    1. Scan data directory for documents
    2. Pre-process files (convert DOCX/CSV → Markdown)
    3. Parse and chunk with Docling hierarchical chunker
    4. Generate parent-level summaries with LLM
    5. Index into Qdrant with full metadata

    Args:
        data_dir: Path to data directory. Uses config default if None.

    Returns:
        IngestResponse with statistics
    """
    settings = get_settings()
    data_dir = data_dir or settings.DATA_DIR

    logger.info(f"Starting ingestion from: {data_dir}")
    update_status("processing", 10, f"Starting ingestion from {data_dir}...")
    
    # Step 1: Scan data directory
    files_info = scan_data_directory(data_dir)
    if not files_info:
        update_status("error", 0, "No documents found.")
        return IngestResponse(
            status="error",
            message=f"No documents found in {data_dir}",
        )

    logger.info(f"Found {len(files_info)} documents to process")

    # Note: We now clear the collection at the very end to prevent downtime.
    all_chunks = []
    documents_processed = 0
    temp_files = []  # Track temp files for cleanup

    for file_info in files_info:
        filepath = file_info["filepath"]
        filename = file_info["filename"]
        collection = file_info["collection"]
        access_roles = file_info["access_roles"]

        logger.info(f"Processing: {filename} (collection={collection})")

        try:
            # Step 2: Pre-process
            processed_path, original_name = preprocess_file(filepath)
            if not processed_path:
                logger.warning(f"Skipping unsupported file: {filename}")
                continue

            if processed_path != filepath:
                temp_files.append(processed_path)

            # Step 3: Chunk
            chunks = create_chunks(
                filepath=processed_path,
                original_filename=original_name,
                collection=collection,
                access_roles=access_roles,
            )

            if chunks:
                all_chunks.extend(chunks)
                documents_processed += 1
                progress = 10 + int((documents_processed / len(files_info)) * 50)
                update_status("processing", progress, f"Created {len(chunks)} chunks from {filename}")
                logger.info(f"  → Created {len(chunks)} chunks from {filename}")
            else:
                logger.warning(f"  → No chunks created from {filename}")

        except Exception as e:
            logger.error(f"Failed to process {filename}: {e}", exc_info=True)

    if not all_chunks:
        return IngestResponse(
            status="error",
            message="No chunks were created from any documents",
            documents_processed=documents_processed,
        )

    # Step 4: Generate parent summaries (temporarily bypassed to fix hangs)
    logger.info("Skipping parent summarization for faster indexing...")
    # try:
    #     all_chunks = generate_parent_summaries(all_chunks)
    # except Exception as e:
    #     logger.warning(f"Parent summarization failed: {e}")

    # Step 5: Index into Qdrant
    logger.info(f"Indexing {len(all_chunks)} chunks into Qdrant...")
    
    # NEW: Ensure collection exists BEFORE we do anything
    try:
        client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION_NAME
        # This will create it if you deleted it manually
        ensure_collection_exists(client, collection_name, vector_size=384)
        
        # Now clear it for a clean re-index
        client.delete_collection(collection_name)
        ensure_collection_exists(client, collection_name, vector_size=384)
        logger.info(f"Refreshed collection: {collection_name}")
    except Exception as e:
        logger.warning(f"Collection reset failed: {e}")
        
    chunks_indexed = index_chunks(all_chunks)
    update_status("completed", 100, f"Successfully indexed {chunks_indexed} chunks.")

    # Cleanup temp files
    for tmp in temp_files:
        try:
            os.remove(tmp)
        except Exception:
            pass

    result = IngestResponse(
        status="success",
        documents_processed=documents_processed,
        chunks_created=chunks_indexed,
        message=f"Successfully indexed {chunks_indexed} chunks from {documents_processed} documents",
    )

    logger.info(f"Ingestion complete: {result.message}")
    return result
