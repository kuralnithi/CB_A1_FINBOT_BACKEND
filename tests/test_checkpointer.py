"""Script to verify LangGraph Postgres Checkpointer functionality."""
import asyncio
import sys
import logging
import uuid
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.services.rag_service import process_query
from app.models import User

async def run_checkpointer_test():
    test_user = User(
        username="finbot_test_user",
        role="c_level",
        extra_roles=["finance"]
    )
    
    session_id = f"test-memory-{uuid.uuid4().hex[:8]}"
    
    print(f"\n🚀 Starting Checkpointer Test [Session: {session_id}]")
    
    # --- STEP 1: First Query ---
    q1 = "Hi, my name is Kural. What is the dividend for FY24?"
    print(f"\n--- Query 1: '{q1}' ---")
    try:
        res1 = await process_query(q1, test_user, session_id)
        print(f"Bot 1: {res1.answer[:50]}...")
    except Exception as e:
        print(f"❌ Q1 Failed: {e}")
        return

    # --- STEP 2: Second Query (Contextual) ---
    q2 = "Wait, what did I say my name was?"
    print(f"\n--- Query 2: '{q2}' (Testing Memory) ---")
    try:
        res2 = await process_query(q2, test_user, session_id)
        print(f"Bot 2: {res2.answer}")
        
        if "Kural" in res2.answer:
            print("\n✅ CHECKPOINTER WORKING: AI remembered your name across requests!")
        else:
            print("\n⚠️ MEMORY DELAY: AI didn't catch the name. Check if Postgres checkpointer is active (not Memory fallback).")
            
    except Exception as e:
        print(f"❌ Q2 Failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_checkpointer_test())
