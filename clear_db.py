import asyncio
import sys
from sqlalchemy import delete
from app.db.models import UserDB
from app.db.session import get_db

async def clear_users():
    async for db in get_db():
        await db.execute(delete(UserDB))
        await db.commit()
        print("Users table cleared.")
        break

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(clear_users())
