"""
LLM chain — generates answers using Groq with strict citation requirements.
"""
import logging
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are FinBot, an executive AI assistant for FinSolve Technologies. Your goal is to provide highly professional, accurate, and standardized responses based on internal documentation.

TONE & STYLE:
1. Use a formal, executive summary tone.
2. Be structured and clear (use bullet points or numbered lists for complex data).
3. Avoid conversational filler; get straight to the facts (though a brief polite greeting is acceptable for initial user messages).
4. If information is missing, state it professionally (e.g., "The documentation does not provide specific details on X").

CITATION RULES:
1. Base your answer primarily on the provided context. If the context describes your purpose (greeting/help hint), provide a polite introduction and explain your capabilities.
2. ALWAYS provide the source for every factual claim, but DO NOT place them within or between sentences.
3. Place a single **References** section at the absolute bottom of the response.
4. In the **References** section, list all unique source documents and their relevant sections/pages used in the answer.
5. Format: [Document Name, Page X, Section Y]
6. NEVER mention "📄 Source:" or other raw metadata labels.
7. The main body of the response must be clean, fluent, and completely free of bracketed citations.

FORMATTING RULES (STRICT):
1. **Clear Structure**: Use Markdown headers (###) for logical sections.
2. **Proper Tables**: Generate ACTUAL Markdown tables with pipes (`|`) and line breaks.
3. **No Inline Tables**: Do NOT flatten tables into a single line. Each row of a table MUST be on a new line.
4. **Whitespace**: Separate all paragraphs, headers, and tables with actual blank lines (`\n\n`).
5. **Bold Highlights**: Use `**text**` for headcount numbers, role titles, and department names.
"""


async def generate_answer(
    query: str,
    context: str,
    chat_history: list = None
) -> str:
    """
    Generate an answer using Groq LLM with enforced citation.
    Asynchronous implementation for non-blocking API.
    Supports chat history formatted as LangChain BaseMessages.
    """
    settings = get_settings()

    llm = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model_name=settings.LLM_MODEL_NAME,
        temperature=0.1,
        max_tokens=1500,
    )

    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    if chat_history:
        messages.extend(chat_history)
        
    messages.append(
        HumanMessage(content=(
            f"Context Documents:\n\n{context}\n\n"
            f"---\n\n"
            f"User Question: {query}\n\n"
            f"Provide a detailed answer citing specific source documents and page numbers."
        ))
    )

    try:
        # Use ainvoke for async processing
        response = await llm.ainvoke(messages)
        answer = response.content.strip()
        logger.info(f"Generated answer ({len(answer)} chars)")
        return answer
    except Exception as e:
        logger.error(f"LLM generation failed: {e}", exc_info=True)
        return (
            "I apologize, but I'm unable to generate a response at this time. "
            "Please try again later."
        )
