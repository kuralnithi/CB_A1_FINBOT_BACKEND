"""Application configuration loaded from environment variables."""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""

    # Groq LLM
    GROQ_API_KEY: str = ""
    LLM_MODEL_NAME: str = "llama-3.3-70b-versatile"

    # Embeddings
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_NAME: str = "finbot_docs"
    QDRANT_COLLECTION_NAME_ROUTES: str = "finbot_routes"

    @property
    def qdrant_is_cloud(self) -> bool:
        """True if QDRANT_HOST looks like a cloud URL (contains http:// or https://)."""
        return self.QDRANT_HOST.startswith("http://") or self.QDRANT_HOST.startswith("https://")

    # JWT
    JWT_SECRET_KEY: str = "your-super-secret-jwt-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # Data
    DATA_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

    # Rate Limiting
    MAX_QUERIES_PER_SESSION: int = 20

    # PostgreSQL Database
    DATABASE_URL: str = "postgresql+psycopg://neondb_owner:npg_2BeX5lpuECnU@ep-aged-union-a47ak6ww-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

    # Admin Setup Defaults
    ADMIN_USER: str = "finbot_admin"
    ADMIN_PASS: str = "ChangeThisPassword123!"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()