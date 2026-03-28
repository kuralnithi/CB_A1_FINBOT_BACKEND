import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        print("1. Creating Admin...")
        res = await client.post("/api/auth/setup-admin")
        print(f"Setup-Admin: {res.status_code} {res.text}")
        
        print("\n2. Logging in as admin...")
        res = await client.post("/api/auth/login", json={"username": "admin", "password": "securepassword"})
        print(f"Login: {res.status_code} {res.text}")
        
        if res.status_code == 200:
            token = res.json()["access_token"]
            
            print("\n3. Testing /api/admin/users GET")
            res_users = await client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
            print(f"Users: {res_users.status_code} {res_users.text}")

if __name__ == "__main__":
    asyncio.run(main())
