"""
LLM Factory — centralizes the instantiation of different LLM providers.
Supports Groq, Ollama, and Google Gemini.
"""
import logging
from typing import Any
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import get_settings

logger = logging.getLogger(__name__)

def get_llm(temperature: float = 0.1, max_tokens: int = 1500) -> Any:
    """
    Factory method to get the configured LLM instance.
    Defaults to settings.LLM_PROVIDER and settings.LLM_MODEL_NAME.
    """
    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower()
    model = settings.LLM_MODEL_NAME

    logger.info(f"Instantiating LLM: provider={provider}, model={model}")

    if provider == "groq":
        if not settings.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY is missing!")
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model_name=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    elif provider == "ollama":
        # Note: ChatOllama handles its own async implementation via LangChain.
        # We omit top-level temperature to avoid a TypeError in the underlying ollama-python library
        # during async calls (where 'temperature' is not a valid direct argument).
        return ChatOllama(
            model=model,
            base_url=settings.OLLAMA_BASE_URL,
        )

    elif provider == "gemini":
        if not settings.GOOGLE_API_KEY:
            logger.warning("GOOGLE_API_KEY is missing!")
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

    else:
        logger.error(f"Unsupported LLM provider: {provider}. Falling back to Groq.")
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model_name="llama-3.1-8b-instant",
            temperature=temperature,
            max_tokens=max_tokens,
        )
