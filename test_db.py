import asyncio
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import UserDB
from app.config import get_settings
from app.api.deps import get_password_hash

async def test_db():
    try:
        settings = get_settings()
        async for db in get_db():
            print("DB connected")
            result = await db.execute(select(UserDB).limit(1))
            res = result.scalar_one_or_none()
            print("DB read:", res)
            
            p = get_password_hash("test")
            print("Hash:", p)
            break
    except Exception as e:
        print("ERROR:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_db())
