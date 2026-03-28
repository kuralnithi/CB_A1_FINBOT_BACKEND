"""
Parent-level summarizer using Groq LLM.

Groups chunks by parent and generates summaries for section-level context.
"""
import logging
from itertools import groupby
from operator import itemgetter
from langchain_groq import ChatGroq
from app.config import get_settings

logger = logging.getLogger(__name__)


def generate_parent_summaries(chunks: list[dict]) -> list[dict]:
    """
    Generate LLM summaries for parent-level sections.

    Groups chunks by parent_chunk_id, summarizes the grouped text,
    and attaches the summary to each child chunk.

    Args:
        chunks: List of dicts with 'text' and 'metadata' keys

    Returns:
        Updated chunks with parent_summary populated
    """
    if not chunks:
        return chunks

    settings = get_settings()

    try:
        llm = ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model_name=settings.LLM_MODEL_NAME,
            temperature=0,
            max_tokens=300,
        )
    except Exception as e:
        logger.error(f"Failed to initialize Groq LLM for summarization: {e}")
        return chunks

    # Group chunks by parent_chunk_id
    sorted_chunks = sorted(chunks, key=lambda c: c["metadata"].parent_chunk_id or "")
    groups = groupby(sorted_chunks, key=lambda c: c["metadata"].parent_chunk_id or "")

    summaries_cache: dict[str, str] = {}

    for parent_id, group_chunks in groups:
        group_list = list(group_chunks)

        if not parent_id or len(group_list) <= 1:
            continue

        # Combine texts for the group
        combined_text = "\n\n".join([c["text"][:500] for c in group_list[:5]])

        if parent_id in summaries_cache:
            summary = summaries_cache[parent_id]
        else:
            try:
                prompt = (
                    "Summarize the following document section in 2-3 concise sentences. "
                    "Focus on the key topics and information covered:\n\n"
                    f"{combined_text[:2000]}"
                )
                response = llm.invoke(prompt)
                summary = response.content.strip()
                summaries_cache[parent_id] = summary
                logger.info(f"Generated summary for parent {parent_id[:8]}...")
            except Exception as e:
                logger.warning(f"Failed to generate summary for parent {parent_id}: {e}")
                summary = ""

        # Attach summary to all children
        for chunk in group_list:
            chunk["metadata"].parent_summary = summary

    logger.info(f"Generated {len(summaries_cache)} parent summaries")
    return chunks
