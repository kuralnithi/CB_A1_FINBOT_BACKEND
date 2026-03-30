"""
Admin API endpoints — document management and system administration.
"""
import logging
import shutil
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.models import User, IngestResponse, DocumentInfo
from app.db.models import UserDB, QueryLog, EvalRun
from app.api.deps import get_current_user
from app.ingestion.pipeline import run_ingestion
from app.ingestion.indexer import get_qdrant_client
from app.rbac.access_control import DEMO_USERS
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Only c_level users can access admin endpoints."""
    if user.role != "c_level":
        raise HTTPException(
            status_code=403,
            detail="Admin access requires c_level role",
        )
    return user


from fastapi import BackgroundTasks

@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingestion(
    background_tasks: BackgroundTasks,
    user: User = Depends(require_admin),
):
    """
    Trigger document re-indexing.

    Scans the data directory, processes all documents, and indexes into Qdrant.
    Requires c_level role.
    """
    logger.info(f"Ingestion triggered by admin: {user.username}")

    try:
        background_tasks.add_task(run_ingestion)
        return IngestResponse(
            status="success",
            message="Ingestion started in the background. This may take a few minutes."
        )
    except Exception as e:
        logger.error(f"Ingestion failed to start: {e}", exc_info=True)
        return IngestResponse(
            status="error",
            message=f"Ingestion failed to start: {str(e)}",
        )


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(
    user: User = Depends(require_admin),
):
    """List all indexed documents with chunk counts."""
    settings = get_settings()

    try:
        client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION_NAME

        # Check if collection exists
        collections = [c.name for c in client.get_collections().collections]
        if collection_name not in collections:
            return []

        # Scroll through all points to aggregate by document
        doc_stats: dict[str, dict] = {}
        offset = None
        batch_size = 100

        while True:
            results, next_offset = client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=["source_document", "collection"],
            )

            for point in results:
                doc_name = point.payload.get("source_document", "unknown")
                collection = point.payload.get("collection", "unknown")

                if doc_name not in doc_stats:
                    doc_stats[doc_name] = {
                        "filename": doc_name,
                        "collection": collection,
                        "chunk_count": 0,
                    }
                doc_stats[doc_name]["chunk_count"] += 1

            if next_offset is None:
                break
            offset = next_offset

        return [DocumentInfo(**stats) for stats in doc_stats.values()]

    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        return []


@router.delete("/documents/{filename}")
async def delete_document(
    filename: str,
    user: User = Depends(require_admin),
):
    """Delete all chunks for a specific document."""
    settings = get_settings()

    try:
        client = get_qdrant_client()
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client.delete(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source_document",
                        match=MatchValue(value=filename),
                    )
                ]
            ),
        )

        logger.info(f"Deleted document '{filename}' from index")
        return {"status": "success", "message": f"Deleted chunks for '{filename}'"}

    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.db.session import get_db
from app.db.models import UserDB
from app.api.deps import get_password_hash
from app.models import UserCreate

@router.get("/users")
async def list_users(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all users in the system."""
    result = await db.execute(select(UserDB))
    db_users = result.scalars().all()
    
    return [
        {
            "username": u.username,
            "role": u.role,
            "display_name": u.display_name,
            "extra_roles": [r for r in (u.extra_roles or "").split(",") if r],
            "created_at": u.created_at
        }
        for u in db_users
    ]

@router.post("/users", response_model=User)
async def create_user(
    new_user: UserCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new user with a specified role."""
    # Check if username exists
    username = new_user.username.lower().strip()
    result = await db.execute(select(UserDB).where(UserDB.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already registered")

    db_user = UserDB(
        username=username,
        hashed_password=get_password_hash(new_user.password),
        role=new_user.role,
        display_name=new_user.display_name
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    logger.info(f"Admin '{user.username}' created new user '{username}' with role '{new_user.role}'")

    return User(
        username=db_user.username,
        role=db_user.role,
        display_name=db_user.display_name
    )


from pydantic import BaseModel as PydanticBase

class RoleUpdate(PydanticBase):
    role: str

VALID_ROLES = {"employee", "finance", "engineering", "marketing", "c_level"}

@router.patch("/users/{username}/role", response_model=User)
async def update_user_role(
    username: str,
    payload: RoleUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update the role of an existing user. Admin only."""
    if payload.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{payload.role}'. Must be one of: {', '.join(VALID_ROLES)}"
        )

    result = await db.execute(select(UserDB).where(UserDB.username == username.lower()))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = db_user.role
    db_user.role = payload.role
    await db.commit()
    await db.refresh(db_user)

    logger.info(f"Admin '{admin.username}' changed '{username}' role: {old_role} → {payload.role}")

    return User(
        username=db_user.username,
        role=db_user.role,
        display_name=db_user.display_name,
        extra_roles=[r for r in (db_user.extra_roles or "").split(",") if r],
    )


class ExtraRolesUpdate(PydanticBase):
    extra_roles: list[str]

@router.patch("/users/{username}/extra-roles")
async def update_user_extra_roles(
    username: str,
    payload: ExtraRolesUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replace the extra access roles for a user. Admin only.
    
    extra_roles is stored as comma-separated string internally.
    Each entry must be a valid role key.
    """
    invalid = [r for r in payload.extra_roles if r not in VALID_ROLES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role(s): {', '.join(invalid)}. Must be from: {', '.join(VALID_ROLES)}"
        )

    result = await db.execute(select(UserDB).where(UserDB.username == username.lower()))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Exclude the user's own primary role from extra_roles to avoid duplication
    cleaned = [r for r in payload.extra_roles if r != db_user.role]
    db_user.extra_roles = ",".join(cleaned)
    await db.commit()
    await db.refresh(db_user)

    logger.info(
        f"Admin '{admin.username}' updated extra roles for '{username}': {cleaned}"
    )

    return {
        "username": db_user.username,
        "role": db_user.role,
        "extra_roles": cleaned,
    }

@router.delete("/users/{username}")
async def delete_user(
    username: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user from the system. Admin only."""
    username = username.lower().strip()
    
    # Prevent admin from deleting themselves
    if username == admin.username.lower().strip():
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
    
    result = await db.execute(select(UserDB).where(UserDB.username == username))
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    await db.delete(db_user)
    await db.commit()
    
    logger.info(f"Admin '{admin.username}' deleted user '{username}'")
    return {"status": "success", "message": f"User '{username}' has been deleted."}


@router.post("/upload", response_class=JSONResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection: str = Form(...),
    user: User = Depends(get_current_user)
):
    """
    Upload a document and trigger ingestion.
    Admin only.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    settings = get_settings()
    
    # Map collection to subfolder
    subfolders = ["general", "finance", "engineering", "marketing", "hr"]
    if collection not in subfolders:
        raise HTTPException(status_code=400, detail=f"Invalid collection. Must be one of: {subfolders}")

    # Ensure target directory exists
    target_dir = Path(settings.DATA_DIR) / collection
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / file.filename
    
    logger.info(f"Uploading file: {file.filename} to {collection}")

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Trigger ingestion
    try:
        # We run the full ingestion for simplicity, 
        # but in a production app we might just process the new file.
        background_tasks.add_task(run_ingestion)
        return {
            "status": "success", 
            "message": f"File '{file.filename}' uploaded successfully. Background ingestion started."
        }
    except Exception as e:
        logger.error(f"Failed to start background ingestion: {e}")
        return {
            "status": "partial_success",
            "message": f"File '{file.filename}' uploaded, but failed to start indexing: {str(e)}"
        }

from app.db.models import QueryLog

@router.get("/queries")
async def list_queries(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List the most recent 50 queries from the audit log."""
    try:
        result = await db.execute(select(QueryLog).order_by(QueryLog.created_at.desc()).limit(50))
        queries = result.scalars().all()
        return [
            {
                "id": q.id,
                "username": q.username,
                "query": q.query,
                "answer": q.answer,
                "user_role": q.user_role,
                "routing_selected": q.routing_selected,
                "is_exported": q.is_exported,
                "created_at": q.created_at.isoformat() if q.created_at else None
            }
            for q in queries
        ]
    except Exception as e:
        logger.error(f"Failed to fetch queries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch queries")

@router.delete("/queries/{query_id}")
async def delete_query_log(
    query_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific query log entry."""
    try:
        await db.execute(delete(QueryLog).where(QueryLog.id == query_id))
        await db.commit()
        logger.info(f"Admin '{user.username}' deleted query log {query_id}")
        return {"status": "success", "message": f"Query log {query_id} deleted."}
    except Exception as e:
        logger.error(f"Failed to delete query log {query_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete query log")

from pydantic import BaseModel

class AddDatasetRequest(BaseModel):
    id: int
    query: str
    answer: str
    ground_truth: str

@router.post("/eval/add-to-dataset")
async def add_query_to_dataset(
    payload: AddDatasetRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Add a query formulation to the LangSmith evaluation dataset and mark as exported."""
    from app.evaluation.langsmith_client import add_to_dataset
    result = add_to_dataset(
        query=payload.query,
        answer=payload.answer,
        ground_truth=payload.ground_truth,
        dataset_name="finbot_eval"
    )
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    # Mark as exported in DB
    try:
        await db.execute(
            update(QueryLog)
            .where(QueryLog.id == payload.id)
            .values(is_exported=True)
        )
        await db.commit()
        logger.info(f"Marked query {payload.id} as exported in DB.")
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to mark query {payload.id} as exported in DB: {e}")
        # We don't raise here because the item was already added to LangSmith,
        # but we add it to the message so the user knows the DB part failed.
        return {"status": "partial_success", "message": "Added to LangSmith, but failed to update local DB status."}
    
    return {"status": "success", "message": "Successfully added to LangSmith golden dataset."}

class BulkAddRequest(BaseModel):
    items: list[AddDatasetRequest]

@router.post("/eval/bulk-add")
async def bulk_add_to_dataset(
    payload: BulkAddRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
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
                dataset_name="finbot_eval"
            )
            if res["status"] == "success":
                await db.execute(
                    update(QueryLog)
                    .where(QueryLog.id == item.id)
                    .values(is_exported=True)
                )
            results.append({"id": item.id, "status": res["status"]})
        
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Bulk promotion DB update failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database update failed during bulk promotion: {str(e)}")
    
    return {"status": "success", "results": results}

@router.post("/eval/run")
async def trigger_eval_run(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Run an evaluation over the LangSmith dataset and persist results."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from app.evaluation.langsmith_client import run_evaluation
    
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, lambda: run_evaluation(dataset_name="finbot_eval"))
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    
    # Persist evaluation results to DB
    try:
        eval_run = EvalRun(
            experiment_name=result.get("experiment_name", "FinBot-Eval"),
            dataset_name="finbot_eval",
            total_examples=result.get("total_examples", 0),
            avg_exact_match=result.get("avg_exact_match"),
            results_url=result.get("results_url"),
            per_example_results=result.get("per_example_results"),
            triggered_by=user.username,
        )
        db.add(eval_run)
        await db.commit()
        await db.refresh(eval_run)
        result["run_id"] = eval_run.id
    except Exception as e:
        logger.error(f"Failed to persist eval run: {e}", exc_info=True)
    
    return result

@router.get("/eval/runs")
async def list_eval_runs(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all past evaluation runs from the database."""
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
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific evaluation run from history."""
    try:
        await db.execute(delete(EvalRun).where(EvalRun.id == run_id))
        await db.commit()
        logger.info(f"Admin '{user.username}' deleted eval run {run_id}")
        return {"status": "success", "message": f"Evaluation run {run_id} deleted."}
    except Exception as e:
        logger.error(f"Failed to delete eval run {run_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete eval run")

class RecommendRequest(BaseModel):
    query: str
    answer: str

@router.post("/eval/recommend-ground-truth")
async def recommend_ground_truth(
    payload: RecommendRequest,
    user: User = Depends(require_admin)
):
    """Use the LLM to suggest a professional ground truth for a query/answer pair."""
    from langchain_groq import ChatGroq
    from app.config import get_settings
    
    settings = get_settings()
    llm = ChatGroq(api_key=settings.GROQ_API_KEY, model_name=settings.LLM_MODEL_NAME)
    
    prompt = f"""
    You are an AI quality engineer. Given a user's query and the bot's current answer, 
    provide a professional, concise, and accurate "Ground Truth" answer that would be suitable 
    for an evaluation dataset. 
    
    If the query is a security violation or off-topic, the ground truth should be a standard refusal.
    
    Query: {payload.query}
    Current Answer: {payload.answer}
    
    Ground Truth (Output only the text of the answer):
    """
    
    try:
        response = await llm.ainvoke(prompt)
        return {"recommendation": response.content.strip()}
    except Exception as e:
        logger.error(f"Failed to recommend ground truth: {e}")
        return {"recommendation": "Error generating recommendation. Please draft manually."}
