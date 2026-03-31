import logging
import sys
from app.ingestion.pipeline import run_ingestion
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
load_dotenv()

print("Starting manual ingestion test...")
try:
    res = run_ingestion()
    print("Result:")
    print(res.model_dump_json(indent=2))
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
