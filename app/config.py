"""
Application configuration loaded from environment variables.

All sensitive defaults are empty strings — real values MUST come from .env.
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings — loaded from .env at startup."""

    # ─── LLM Configuration ──────────────────────────────────────────────────
    LLM_PROVIDER: str = "groq"  # options: "groq", "ollama", "gemini"
    LLM_MODEL_NAME: str = "llama-3.1-8b-instant"
    GROQ_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    GOOGLE_API_KEY: str = ""

    # ─── Embeddings ───────────────────────────────────────────────────────────
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"

    # ─── Qdrant ───────────────────────────────────────────────────────────────
    QDRANT_HOST: str = ""
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_NAME: str = "finbot_docs"
    QDRANT_COLLECTION_NAME_ROUTES: str = "finbot_routes"

    @property
    def qdrant_is_cloud(self) -> bool:
        """True if QDRANT_HOST looks like a cloud URL."""
        return self.QDRANT_HOST.startswith("http://") or self.QDRANT_HOST.startswith("https://")

    # ─── JWT ──────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # ─── Data ─────────────────────────────────────────────────────────────────
    DATA_DIR: str = str(Path(__file__).resolve().parents[1] / "data")

    # ─── Rate Limiting ────────────────────────────────────────────────────────
    MAX_QUERIES_PER_SESSION: int = 20

    # ─── PostgreSQL ───────────────────────────────────────────────────────────
    DATABASE_URL: str = ""

    # ─── Admin Bootstrap ──────────────────────────────────────────────────────
    ADMIN_USER: str = "finbot_admin"
    ADMIN_PASS: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()