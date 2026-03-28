"""
Context builder — formats retrieved chunks into LLM-ready context.
"""
import logging

logger = logging.getLogger(__name__)


def build_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a structured context for the LLM.

    Each chunk is formatted with source attribution for citation enforcement.

    Args:
        chunks: List of retrieved chunk dicts

    Returns:
        Formatted context string
    """
    if not chunks:
        return "No relevant documents were found for your query."

    context_parts = []

    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_document", "Unknown")
        page = chunk.get("page_number", 0)
        section = chunk.get("section_title", "")
        chunk_type = chunk.get("chunk_type", "text")
        text = chunk.get("text", "")
        parent_summary = chunk.get("parent_summary", "")

        header = f"[Source {i}: {source}"
        if page:
            header += f", Page {page}"
        if section:
            header += f", Section: {section}"
        header += f", Type: {chunk_type}]"

        part = header + "\n"
        if parent_summary:
            part += f"[Context: {parent_summary}]\n"
        part += text

        context_parts.append(part)

    context = "\n\n---\n\n".join(context_parts)

    logger.info(f"Built context from {len(chunks)} chunks ({len(context)} chars)")
    return context
