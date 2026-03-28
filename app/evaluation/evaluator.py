"""
RAGAS evaluation runner with ablation study.

Evaluates the RAG pipeline using faithfulness, answer_relevancy,
context_precision, context_recall, and answer_correctness.
"""
import logging
import json
from datetime import datetime

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    faithfulness,
    context_precision,
    context_recall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceBgeEmbeddings

from app.config import get_settings
from app.models import User
from app.services.rag_service import process_query
from app.evaluation.dataset import EVALUATION_DATASET

logger = logging.getLogger(__name__)


def _get_ragas_llm():
    """Get LLM wrapper for RAGAS evaluation."""
    settings = get_settings()
    llm = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model_name=settings.LLM_MODEL_NAME,
        temperature=0,
    )
    return LangchainLLMWrapper(llm)


def _get_ragas_embeddings():
    """Get embeddings wrapper for RAGAS evaluation."""
    settings = get_settings()
    embeddings = HuggingFaceBgeEmbeddings(
        model_name=settings.EMBEDDING_MODEL_NAME,
    )
    return LangchainEmbeddingsWrapper(embeddings)


def run_evaluation(
    skip_rbac: bool = False,
    skip_router: bool = False,
    skip_guardrails: bool = False,
    label: str = "full_pipeline",
) -> dict:
    """
    Run RAGAS evaluation on the pipeline.

    Args:
        skip_rbac: If True, bypass RBAC checks (ablation)
        skip_router: If True, bypass semantic routing (ablation)
        skip_guardrails: If True, bypass guardrails (ablation)
        label: Label for this evaluation run

    Returns:
        Dict with metric scores and per-question results
    """
    settings = get_settings()
    logger.info(f"Starting RAGAS evaluation: {label}")

    questions = []
    ground_truths = []
    answers = []
    contexts = []

    for entry in EVALUATION_DATASET:
        question = entry["question"]
        ground_truth = entry["ground_truth"]
        test_role = entry["test_role"]

        # Skip RBAC boundary tests for ablation without RBAC
        if ground_truth.startswith("RBAC_DENY") and skip_rbac:
            continue
        if ground_truth.startswith("GUARDRAIL_BLOCK") and skip_guardrails:
            continue

        user = User(username=test_role, role=test_role, display_name=test_role)

        try:
            response = process_query(
                query=question,
                user=user,
                session_id=f"eval_{label}_{test_role}",
            )

            answer = response.answer or "No answer generated"
            retrieved_contexts = [
                f"{s.document} (Page {s.page_number}): {s.section}"
                for s in response.sources
            ] if response.sources else ["No context retrieved"]

        except Exception as e:
            logger.error(f"Eval query failed: {question} — {e}")
            answer = f"Error: {str(e)}"
            retrieved_contexts = ["Error during retrieval"]

        questions.append(question)
        ground_truths.append(ground_truth)
        answers.append(answer)
        contexts.append(retrieved_contexts)

    # Build RAGAS dataset
    eval_dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    # Run RAGAS
    try:
        ragas_llm = _get_ragas_llm()
        ragas_embeddings = _get_ragas_embeddings()

        results = evaluate(
            dataset=eval_dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
                answer_correctness,
            ],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
        )

        scores = {
            "label": label,
            "timestamp": datetime.now().isoformat(),
            "num_questions": len(questions),
            "metrics": {
                "faithfulness": float(results["faithfulness"]),
                "answer_relevancy": float(results["answer_relevancy"]),
                "context_precision": float(results["context_precision"]),
                "context_recall": float(results["context_recall"]),
                "answer_correctness": float(results["answer_correctness"]),
            },
        }

        logger.info(f"RAGAS results [{label}]: {json.dumps(scores['metrics'], indent=2)}")
        return scores

    except Exception as e:
        logger.error(f"RAGAS evaluation failed: {e}", exc_info=True)
        return {
            "label": label,
            "error": str(e),
            "num_questions": len(questions),
        }


def run_ablation_study() -> list[dict]:
    """
    Run ablation study with 4 configurations:
    1. Full pipeline
    2. Without RBAC
    3. Without Router
    4. Without Guardrails
    """
    logger.info("Starting ablation study...")

    results = []

    # Config 1: Full pipeline
    results.append(run_evaluation(label="full_pipeline"))

    # Config 2: Without RBAC
    results.append(run_evaluation(skip_rbac=True, label="without_rbac"))

    # Config 3: Without Router
    results.append(run_evaluation(skip_router=True, label="without_router"))

    # Config 4: Without Guardrails
    results.append(run_evaluation(skip_guardrails=True, label="without_guardrails"))

    # Save results
    try:
        output_path = "evaluation_results.json"
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Ablation results saved to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save results: {e}")

    return results
