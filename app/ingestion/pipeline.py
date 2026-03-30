"""
Ingestion pipeline orchestrator.

Scans data directory → parses → chunks → summarizes → indexes.
"""
import os
import logging
from pathlib import Path

from app.ingestion.parser import scan_data_directory, preprocess_file
from app.ingestion.chunker import create_chunks
from app.ingestion.summarizer import generate_parent_summaries
from app.ingestion.indexer import index_chunks, get_qdrant_client
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

    # Step 1: Scan data directory
    files_info = scan_data_directory(data_dir)
    if not files_info:
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

    # Step 4: Generate parent summaries
    logger.info("Generating parent-level summaries...")
    try:
        all_chunks = generate_parent_summaries(all_chunks)
    except Exception as e:
        logger.warning(f"Parent summarization failed (continuing without): {e}")

    # Step 5: Index into Qdrant
    logger.info(f"Indexing {len(all_chunks)} chunks into Qdrant...")
    
    # Clear existing collection right before inserting new chunks to prevent downtime
    try:
        client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION_NAME
        collections = [c.name for c in client.get_collections().collections]
        if collection_name in collections:
            client.delete_collection(collection_name)
            logger.info(f"Deleted existing collection: {collection_name}")
    except Exception as e:
        logger.warning(f"Could not clear collection before indexing: {e}")
        
    chunks_indexed = index_chunks(all_chunks)

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
