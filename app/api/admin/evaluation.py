"""
Admin API — Evaluation & LangSmith integration endpoints.

Handles dataset promotion, evaluation runs, progress tracking, and AI-powered
ground truth recommendation.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.api.deps import get_current_user
from app.db.session import get_db, AsyncSessionLocal
from app.db.models import QueryLog, EvalRun
from app.evaluation.status_tracker import update_eval_status, get_eval_status, reset_eval_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin — Evaluation"])


# ─── Dependencies ─────────────────────────────────────────────────────────────


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "c_level":
        raise HTTPException(status_code=403, detail="Admin access requires c_level role")
    return user


# ─── Schemas ──────────────────────────────────────────────────────────────────


class AddDatasetRequest(BaseModel):
    """Payload for promoting a single query to the LangSmith dataset."""
    id: int
    query: str
    answer: str
    ground_truth: str


class BulkAddRequest(BaseModel):
    """Payload for promoting multiple queries at once."""
    items: list[AddDatasetRequest]


class RecommendRequest(BaseModel):
    """Payload for AI-powered ground truth recommendation."""
    query: str
    answer: str


# ─── Dataset Promotion ────────────────────────────────────────────────────────


@router.post("/eval/add-to-dataset")
async def add_query_to_dataset(
    payload: AddDatasetRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a query to the LangSmith evaluation dataset and mark as exported."""
    from app.evaluation.langsmith_client import add_to_dataset

    result = add_to_dataset(
        query=payload.query,
        answer=payload.answer,
        ground_truth=payload.ground_truth,
        dataset_name="finbot_eval",
    )
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    try:
        await db.execute(update(QueryLog).where(QueryLog.id == payload.id).values(is_exported=True))
        await db.commit()
        logger.info(f"Marked query {payload.id} as exported.")
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to mark query {payload.id} as exported: {e}")
        return {"status": "partial_success", "message": "Added to LangSmith, but DB update failed."}

    return {"status": "success", "message": "Added to LangSmith golden dataset."}


@router.post("/eval/bulk-add")
async def bulk_add_to_dataset(
    payload: BulkAddRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Promote multiple queries to LangSmith and mark them as exported."""
    from app.evaluation.langsmith_client import add_to_dataset

    results = []
    try:
        for item in payload.items:
            res = add_to_dataset(
                query=item.query,
                answer=item.answer,
                ground_truth=item.ground_truth,
                dataset_name="finbot_eval",
            )
            if res["status"] == "success":
                await db.execute(update(QueryLog).where(QueryLog.id == item.id).values(is_exported=True))
            results.append({"id": item.id, "status": res["status"]})

        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Bulk promotion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk promotion failed: {e}")

    return {"status": "success", "results": results}


# ─── Background Evaluation ────────────────────────────────────────────────────


async def _bg_run_evaluation(username: str):
    """Background task: run LangSmith evaluation and persist results to DB."""
    from app.evaluation.langsmith_client import run_evaluation

    try:
        result = run_evaluation(dataset_name="finbot_eval")

        if result["status"] == "success":
            async with AsyncSessionLocal() as db:
                eval_run = EvalRun(
                    experiment_name=result.get("experiment_name", "FinBot-Eval"),
                    dataset_name="finbot_eval",
                    total_examples=result.get("total_examples", 0),
                    avg_exact_match=result.get("avg_exact_match"),
                    results_url=result.get("results_url"),
                    per_example_results=result.get("per_example_results"),
                    triggered_by=username,
                )
                db.add(eval_run)
                await db.commit()

            update_eval_status(status="completed", message="Evaluation successful!")
        else:
            update_eval_status(status="error", message=result.get("message", "Unknown error"))

    except Exception as e:
        logger.error(f"Background evaluation failed: {e}", exc_info=True)
        update_eval_status(status="error", message=str(e))


@router.post("/eval/run")
async def trigger_eval_run(
    background_tasks: BackgroundTasks,
    user: User = Depends(require_admin),
):
    """Trigger a LangSmith evaluation run in the background."""
    reset_eval_status()
    update_eval_status(status="initializing", message="Queueing evaluation task...")
    background_tasks.add_task(_bg_run_evaluation, user.username)
    return {"status": "success", "message": "Evaluation started in background."}


@router.get("/eval/status")
async def get_eval_run_status(user: User = Depends(require_admin)):
    """Get the current progress of the background evaluation."""
    return get_eval_status()


# ─── Evaluation History ───────────────────────────────────────────────────────


@router.get("/eval/runs")
async def list_eval_runs(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all past evaluation runs."""
    result = await db.execute(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(20))
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "experiment_name": r.experiment_name,
            "dataset_name": r.dataset_name,
            "total_examples": r.total_examples,
            "avg_exact_match": r.avg_exact_match,
            "results_url": r.results_url,
            "per_example_results": r.per_example_results,
            "triggered_by": r.triggered_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ]


@router.delete("/eval/runs/{run_id}")
async def delete_eval_run(
    run_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific evaluation run from history."""
    try:
        await db.execute(delete(EvalRun).where(EvalRun.id == run_id))
        await db.commit()
        logger.info(f"Admin '{user.username}' deleted eval run {run_id}")
        return {"status": "success", "message": f"Eval run {run_id} deleted."}
    except Exception as e:
        logger.error(f"Failed to delete eval run {run_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete eval run")


# ─── Ground Truth Recommendation ──────────────────────────────────────────────


@router.post("/eval/recommend-ground-truth")
async def recommend_ground_truth(
    payload: RecommendRequest,
    user: User = Depends(require_admin),
):
    """Use the LLM to suggest a professional ground truth for evaluation."""
    from langchain_groq import ChatGroq
    from app.config import get_settings

    settings = get_settings()
    llm = ChatGroq(api_key=settings.GROQ_API_KEY, model_name=settings.LLM_MODEL_NAME)

    prompt = f"""You are an AI quality engineer. Given a user's query and the bot's current answer,
provide a professional, concise, and accurate "Ground Truth" answer suitable for an evaluation dataset.
If the query is a security violation or off-topic, the ground truth should be a standard refusal.

Query: {payload.query}
Current Answer: {payload.answer}

Ground Truth (output only the text):"""

    try:
        response = await llm.ainvoke(prompt)
        return {"recommendation": response.content.strip()}
    except Exception as e:
        logger.error(f"Failed to recommend ground truth: {e}")
        return {"recommendation": "Error generating recommendation. Please draft manually."}
