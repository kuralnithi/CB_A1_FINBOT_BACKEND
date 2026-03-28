"""Create checkpoint tables using Neon DIRECT (non-pooler) endpoint."""
import asyncio
import sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Use DIRECT endpoint (remove -pooler from hostname)
DIRECT_URL = "postgresql://neondb_owner:npg_2BeX5lpuECnU@ep-aged-union-a47ak6ww.us-east-1.aws.neon.tech/neondb?sslmode=require"

async def setup():
    print(f"Connecting to DIRECT endpoint...")
    async with AsyncPostgresSaver.from_conn_string(DIRECT_URL) as cp:
        print("Connected! Running setup()...")
        await cp.setup()
        print("✅ Checkpoint tables created successfully!")

asyncio.run(setup())
