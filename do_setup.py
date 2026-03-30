"""
Initial system setup script.
Creates the admin user and ensures Qdrant collections exist.
Runs directly against the database/vector store (no HTTP requests needed).
"""
import asyncio
import logging
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import UserDB
from app.api.deps import get_password_hash
from app.config import get_settings
from app.ingestion.indexer import get_qdrant_client, ensure_collection_exists

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def setup_admin(db):
    """Create initial admin user if no users exist."""
    settings = get_settings()
    
    # Check if any user exists
    result = await db.execute(select(UserDB).limit(1))
    if result.scalar_one_or_none():
        logger.info("Admin setup skipped: Users already exist in the database.")
        return

    # Create admin
    admin_user = UserDB(
        username=settings.ADMIN_USER,
        hashed_password=get_password_hash(settings.ADMIN_PASS),
        role="c_level",
        display_name="System Administrator"
    )
    db.add(admin_user)
    await db.commit()
    logger.info(f"Initial setup: Admin user '{settings.ADMIN_USER}' created.")

def setup_qdrant():
    """Ensure required Qdrant collections exist."""
    settings = get_settings()
    client = get_qdrant_client()
    
    # Primary document collection
    ensure_collection_exists(client, settings.QDRANT_COLLECTION_NAME, vector_size=384)
    
    # Semantic router collection
    ensure_collection_exists(client, settings.QDRANT_COLLECTION_NAME_ROUTES, vector_size=384)
    
    logger.info("Qdrant collections verified/created.")

async def run_setup():
    """Main setup entrypoint."""
    logger.info("🚀 Starting FinBot initial system setup...")
    
    # 1. Database Setup
    if AsyncSessionLocal:
        async with AsyncSessionLocal() as db:
            await setup_admin(db)
    else:
        logger.warning("Database session not initialized. Skipping admin setup.")

    # 2. Qdrant Setup
    try:
        setup_qdrant()
    except Exception as e:
        logger.error(f"Qdrant setup failed: {e}")

    logger.info("✅ System setup complete.")

if __name__ == "__main__":
    asyncio.run(run_setup())
