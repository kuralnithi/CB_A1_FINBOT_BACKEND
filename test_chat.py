"""Quick test to debug the chat pipeline."""
import requests
import time

BASE = "http://localhost:8000"

# 1. Login
print("1. Logging in...")
r = requests.post(f"{BASE}/api/auth/login", json={
    "username": "finbot_admin",
    "password": "ChangeThisPassword123!"
})
print(f"   Login status: {r.status_code}")
token = r.json()["access_token"]
print(f"   Token: {token[:20]}...")

# 2. Send chat
print("\n2. Sending chat query 'hello'...")
start = time.time()
r = requests.post(
    f"{BASE}/api/chat",
    json={"query": "hello", "session_id": "debug-test-001"},
    headers={"Authorization": f"Bearer {token}"},
    timeout=60,
)
elapsed = time.time() - start
print(f"   Status: {r.status_code} ({elapsed:.1f}s)")
print(f"   Response: {r.json()}")
