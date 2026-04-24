import asyncio
import sys
import logging
import json
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.evaluation.evaluator import run_evaluation

async def main():
    print("\n--- Starting RAGAS Evaluation Test ---")
    print("Note: This uses the models defined in your .env (GROQ_API_KEY is required)\n")
    
    try:
        # Run a small evaluation (limit to 2 questions for a quick smoke test)
        # Change limit=None to run the full dataset (~45 questions)
        limit = 1
        print(f"Running evaluation with limit={limit}...")
        
        results = await run_evaluation(limit=limit, label="smoke_test")
        
        print("\n--- Evaluation Results ---")
        print(json.dumps(results, indent=2))
        
        if "error" in results:
            print(f"\n❌ Evaluation failed with error: {results['error']}")
        else:
            print("\n✅ Evaluation completed successfully!")
            
    except Exception as e:
        print(f"\n❌ Script failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
