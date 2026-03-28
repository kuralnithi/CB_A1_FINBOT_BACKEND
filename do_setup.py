import asyncio
import httpx
import sys

async def run_setup():
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post("http://localhost:8000/api/auth/setup-admin", timeout=10.0)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_setup())
