import os
import logging
from langsmith import Client

logger = logging.getLogger(__name__)

def get_client() -> Client:
    """Initialize LangSmith client, handles API key checking implicitly if set in env."""
    return Client()


def add_to_dataset(query: str, answer: str, ground_truth: str, dataset_name: str = "finbot_eval"):
    """
    Push a specific user query and answer to a LangSmith evaluation dataset.
    Creates the dataset if it does not exist.
    """
    logger.info(f"Adding example to dataset '{dataset_name}'")
    try:
        client = get_client()
        
        # Check if dataset exists, if not create it
        datasets = list(client.list_datasets(dataset_name=dataset_name))
        if not datasets:
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description="Evaluation dataset for FinBot RAG pipeline"
            )
        else:
            dataset = datasets[0]

        # Add the example
        client.create_example(
            inputs={"question": query},
            outputs={"answer": ground_truth},
            dataset_id=dataset.id,
        )
        return {"status": "success", "message": "Successfully added to LangSmith"}
    except Exception as e:
        logger.error(f"Failed to add to LangSmith dataset: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def run_evaluation(dataset_name: str = "finbot_eval"):
    """
    Trigger an evaluation of the RAG pipeline using LangSmith.
    Returns rich results including per-example scores and aggregate metrics.
    """
    logger.info(f"Triggering LangSmith evaluation on '{dataset_name}'")
    try:
        client = get_client()
        
        # Check if dataset exists
        datasets = list(client.list_datasets(dataset_name=dataset_name))
        if not datasets:
            return {"status": "error", "message": "Dataset not found. Please add examples first."}
            
        dataset = datasets[0]
        
        from langsmith.evaluation import evaluate
        from langsmith.schemas import Run, Example
        from app.services.rag_service import process_query
        from app.models import User
        from sentence_transformers import SentenceTransformer, util
        import torch
        
        # ─── REAL-TIME PROGRESS TRACKING ───────────────────
        from app.evaluation.status_tracker import update_eval_status, reset_eval_status
        reset_eval_status()
        
        # Get total number of examples for progress bar
        total_examples = sum(1 for _ in client.list_examples(dataset_id=dataset.id))
        update_eval_status(status="running", total=total_examples, message="Initializing evaluation...")
        
        # Counter for progress
        processed_count = 0

        # Load a small, fast model for semantic similarity
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Per-example ledger for saving to our DB
        per_example_log = []

        def similarity_evaluator(run: Run, example: Example) -> dict:
            actual = (run.outputs or {}).get("answer", "") or ""
            expected = (example.outputs or {}).get("answer", "") or ""
            
            # Direct exact match check first for 1.0 score
            if actual.strip().lower() == expected.strip().lower():
                score = 1.0
            else:
                # Compute semantic similarity
                embeddings = model.encode([actual, expected], convert_to_tensor=True)
                score = float(util.cos_sim(embeddings[0], embeddings[1])[0][0])
                # Ensure it's in 0-1 range (cosine similarity can be negative)
                score = max(0.0, score)
            
            per_example_log.append({
                "query": (example.inputs or {}).get("question", ""),
                "ground_truth": expected,
                "actual_answer": actual,
                "score": round(score, 4)
            })
            return {"key": "semantic_similarity", "score": score}

        # NOTE: This function runs inside a ThreadPoolExecutor — use a fresh event loop.
        import asyncio

        def rag_pipeline(inputs: dict) -> dict:
            nonlocal processed_count
            user = User(username="evaluator", role="c_level", display_name="LangSmith")
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(
                    process_query(query=inputs["question"], user=user, session_id="langsmith_eval")
                )
                loop.close()
                
                # Update progress
                processed_count += 1
                update_eval_status(
                    current=processed_count, 
                    message=f"Testing: {inputs['question'][:30]}..."
                )
                
                return {"answer": response.answer}
            except Exception as e:
                logger.error(f"Error evaluating pipeline input: {e}")
                return {"answer": f"Error: {str(e)}"}

        # Run evaluation
        experiment_results = evaluate(
            rag_pipeline,
            data=dataset_name,
            evaluators=[similarity_evaluator],
            experiment_prefix="FinBot-Eval",
            max_concurrency=1 # Force serial execution to keep progress bar smooth and avoid DB lock issues
        )

        # Compute aggregate score
        total = len(per_example_log)
        avg_score = round(sum(r["score"] for r in per_example_log) / total, 4) if total > 0 else None
        experiment_name = getattr(experiment_results, "experiment_name", f"FinBot-Eval-{dataset_name}")
        results_url = getattr(experiment_results, "url", None)
        
        import json
        return {
            "status": "success",
            "message": f"Evaluation complete — {total} examples tested.",
            "experiment_name": experiment_name,
            "total_examples": total,
            "avg_exact_match": avg_score, # Keeping key name for DB compatibility
            "results_url": results_url,
            "per_example_results": json.dumps(per_example_log),
        }
            
    except Exception as e:
        logger.error(f"Failed to run LangSmith evaluation: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
