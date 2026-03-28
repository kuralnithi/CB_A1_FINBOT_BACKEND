"""
Hierarchical chunker using Docling.

Parses documents into structural hierarchy and creates chunks
with full metadata for RBAC-aware retrieval.
"""
import uuid
import logging
from pathlib import Path
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker import HierarchicalChunker

from app.models import ChunkMetadata

logger = logging.getLogger(__name__)


def create_chunks(
    filepath: str,
    original_filename: str,
    collection: str,
    access_roles: list[str],
) -> list[dict]:
    """
    Parse a document with Docling and create hierarchical chunks.

    Args:
        filepath: Path to the file (may be a converted .md file)
        original_filename: Original document filename
        collection: Collection this document belongs to
        access_roles: Roles that can access this document

    Returns:
        List of dicts with 'text' and 'metadata' keys
    """
    chunks = []

    try:
        # Parse document with Docling
        converter = DocumentConverter()
        result = converter.convert(filepath)
        doc = result.document

        # Apply hierarchical chunking
        chunker = HierarchicalChunker(
            max_tokens=512,
            overlap=50,
        )
        doc_chunks = list(chunker.chunk(doc))

        logger.info(f"Created {len(doc_chunks)} chunks from {original_filename}")

        # Generate a parent ID for the document level
        doc_parent_id = str(uuid.uuid4())

        for i, chunk in enumerate(doc_chunks):
            chunk_id = str(uuid.uuid4())
            chunk_text = chunk.text if hasattr(chunk, "text") else str(chunk)

            if not chunk_text.strip():
                continue

            # Extract hierarchy information from chunk metadata
            section_title = ""
            page_number = 0
            chunk_type = "text"
            hierarchy_path = [original_filename]
            parent_chunk_id = doc_parent_id

            # Try to extract metadata from Docling chunk
            if hasattr(chunk, "meta"):
                meta = chunk.meta
                if hasattr(meta, "headings") and meta.headings:
                    section_title = meta.headings[-1] if meta.headings else ""
                    hierarchy_path.extend(meta.headings)
                if hasattr(meta, "page"):
                    page_number = meta.page or 0
                if hasattr(meta, "doc_items") and meta.doc_items:
                    for item in meta.doc_items:
                        label = getattr(item, "label", "")
                        if label:
                            label_lower = str(label).lower()
                            if "table" in label_lower:
                                chunk_type = "table"
                            elif "code" in label_lower:
                                chunk_type = "code"
                            elif "head" in label_lower or "title" in label_lower:
                                chunk_type = "heading"
                        # Extract page number from prov if available
                        if hasattr(item, "prov") and item.prov:
                            for prov in item.prov:
                                if hasattr(prov, "page_no"):
                                    page_number = prov.page_no or page_number

            metadata = ChunkMetadata(
                chunk_id=chunk_id,
                source_document=original_filename,
                collection=collection,
                access_roles=access_roles,
                section_title=section_title,
                page_number=page_number,
                chunk_type=chunk_type,
                parent_chunk_id=parent_chunk_id,
                hierarchy_path=hierarchy_path,
                parent_summary="",  # Will be filled by summarizer
            )

            chunks.append({
                "text": chunk_text,
                "metadata": metadata,
            })

    except Exception as e:
        logger.error(f"Error chunking {original_filename}: {e}", exc_info=True)
        # Fallback: create a single chunk from the file
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
            if text.strip():
                chunk_id = str(uuid.uuid4())
                metadata = ChunkMetadata(
                    chunk_id=chunk_id,
                    source_document=original_filename,
                    collection=collection,
                    access_roles=access_roles,
                    section_title="Full Document",
                    page_number=1,
                    chunk_type="text",
                    parent_chunk_id=None,
                    hierarchy_path=[original_filename],
                    parent_summary="",
                )
                # Split into reasonable chunks if too large
                max_chars = 2000
                for j in range(0, len(text), max_chars):
                    sub_text = text[j:j + max_chars]
                    sub_id = str(uuid.uuid4())
                    sub_meta = metadata.model_copy(update={"chunk_id": sub_id})
                    chunks.append({"text": sub_text, "metadata": sub_meta})
                logger.info(f"Fallback: created {len(chunks)} chunks from {original_filename}")
        except Exception as fallback_err:
            logger.error(f"Fallback chunking failed for {original_filename}: {fallback_err}")

    return chunks
