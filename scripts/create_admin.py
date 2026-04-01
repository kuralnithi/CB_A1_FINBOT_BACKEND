"""
Dedicated script to create or restore the admin user.
Usage: python scripts/create_admin.py
"""
import asyncio
import logging
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import UserDB
from app.api.deps import get_password_hash
from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_or_restore_admin():
    """Create or update the admin user from environment variables."""
    settings = get_settings()
    username = settings.ADMIN_USER.lower().strip()
    
    if not AsyncSessionLocal:
        logger.error("Database session not initialized. Check your DATABASE_URL.")
        return

    async with AsyncSessionLocal() as db:
        # Check if the specific admin user exists
        result = await db.execute(select(UserDB).where(UserDB.username == username))
        admin_user = result.scalar_one_or_none()

        if admin_user:
            logger.info(f"Admin user '{username}' already exists. Updating password and ensuring 'c_level' role...")
            admin_user.hashed_password = get_password_hash(settings.ADMIN_PASS)
            admin_user.role = "c_level"
            admin_user.display_name = "System Administrator"
        else:
            logger.info(f"Creating admin user '{username}'...")
            admin_user = UserDB(
                username=username,
                hashed_password=get_password_hash(settings.ADMIN_PASS),
                role="c_level",
                display_name="System Administrator"
            )
            db.add(admin_user)
        
        await db.commit()
        logger.info(f"✅ Admin user '{username}' is now ready.")

if __name__ == "__main__":
    asyncio.run(create_or_restore_admin())
