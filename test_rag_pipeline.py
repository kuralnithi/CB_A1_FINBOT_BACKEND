"""Script to trace the exact error in the RAG pipeline."""
import asyncio
import sys
import logging
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.services.rag_service import process_query
from app.models import User

async def run_test():
    test_user = User(
        username="finbot_admin",
        role="c_level",
        extra_roles=["engineering", "finance"]
    )
    
    query = "tell me about engineering department"
    session_id = "test_session_1"
    
    print(f"\n--- Testing Query: '{query}' ---")
    try:
        response = await process_query(query, test_user, session_id)
        print("\n✅ Success!")
        print(f"Answer: {response.answer[:100]}...")
        print(f"Sources: {len(response.sources)}")
        print(f"Collections: {response.accessible_collections}")
    except Exception as e:
        print("\n❌ Pipeline Crashed!")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
