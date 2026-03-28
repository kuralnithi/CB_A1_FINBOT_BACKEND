"""
RAG service — orchestrates the full query pipeline.

Flow: Input Guardrails → Router → RBAC Check → Retrieval → Context → LLM → Output Guardrails
"""
import logging
import time

from app.models import ChatResponse, User, GuardrailWarning
from app.guardrails.input_guards import run_input_guardrails
from app.guardrails.output_guards import run_output_guardrails
from app.router.query_router import route_query
from app.rbac.access_control import get_accessible_collections
from app.retrieval.retriever import retrieve_chunks
from app.retrieval.context_builder import build_context
from app.retrieval.llm_chain import generate_answer

from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, AnyMessage
from app.config import get_settings

logger = logging.getLogger(__name__)

class PipelineState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    query: str
    user: Any
    session_id: str
    response: Any


async def pipeline_node(state: PipelineState) -> dict:
    """Core RAG pipeline execution."""
    query = state.get("query", "")
    user_state = state.get("user")
    session_id = state.get("session_id", "unknown")
    chat_history = state.get("messages", [])[:-1]  # Exclude current human message
    
    start_time = time.perf_counter()

    # Robust State Re-hydration: handle dict vs object
    if isinstance(user_state, dict):
        user = User(**user_state)
    elif hasattr(user_state, "role"):
        user = user_state
    else:
        # Fallback for unexpected state
        logger.warning(f"[PIPELINE] Unexpected user state type: {type(user_state)}")
        user = User(username="unknown", role="employee")

    # Ensure extra_roles is always a list for RBAC
    extra_roles = getattr(user, "extra_roles", []) or []

    accessible_collections = get_accessible_collections(user.role, extra_roles)

    response = ChatResponse(
        user_role=user.role,
        accessible_collections=accessible_collections,
    )

    try:
        # ─── Step 1: Input Guardrails ──────────────────────────────────────────
        step_start = time.perf_counter()
        logger.info(f"[PIPELINE] Step 1: Input guardrails — user={user.username}")

        input_warnings = run_input_guardrails(query, session_id)
        if input_warnings:
            has_error = any(w.severity == "error" for w in input_warnings)
            if has_error:
                response.blocked = True
                response.blocked_reason = input_warnings[0].message
                response.guardrail_warnings = input_warnings
                response.answer = input_warnings[0].message
                logger.warning(f"[PIPELINE] Blocked by input guardrails: {input_warnings[0].type}")
                return {"messages": [AIMessage(content=response.answer)], "response": response}
            response.guardrail_warnings.extend(input_warnings)
        
        logger.debug(f"Step 1 completed in {time.perf_counter() - step_start:.3f}s")

        # ─── Step 2: Semantic Routing ──────────────────────────────────────────
        step_start = time.perf_counter()
        logger.info(f"[PIPELINE] Step 2: Semantic routing")

        route_name, target_collections, denial_message = route_query(query, user.role, extra_roles)
        response.route_selected = route_name
        logger.debug(f"Step 2 completed in {time.perf_counter() - step_start:.3f}s")

        # ─── Step 3: RBAC Check ───────────────────────────────────────────────
        if denial_message:
            response.blocked = True
            response.blocked_reason = denial_message
            response.answer = denial_message
            response.guardrail_warnings.append(GuardrailWarning(
                type="rbac",
                message=denial_message,
                severity="error",
            ))
            logger.warning(f"[PIPELINE] Blocked by RBAC: {denial_message}")
            return {"messages": [AIMessage(content=response.answer)], "response": response}

        # ─── Step 4: Retrieval ───────────────────────────────────────────────
        step_start = time.perf_counter()
        
        if route_name == "greetings_route":
            logger.info("[PIPELINE] Skipping retrieval for greetings_route")
            chunks, citations = [], []
        else:
            logger.info(f"[PIPELINE] Step 4: Retrieval — collections={target_collections}")
            chunks, citations = await retrieve_chunks(
                query=query,
                role=user.role,
                target_collections=target_collections,
                extra_roles=extra_roles,
                top_k=5,
            )
        
        response.sources = citations
        logger.debug(f"Step 4 completed in {time.perf_counter() - step_start:.3f}s")

        if not chunks:
            if route_name == "greetings_route":
                # Very simple synthetic context for greetings
                context = (
                    "The user is just greeting you or saying hi. "
                    "Briefly introduce yourself as FinBot from FinSolve Technologies. "
                    "Keep it short and professional, and ask how you can help with company documentation."
                )
                logger.info("[PIPELINE] Using minimal synthetic context for greetings")
            else:
                response.answer = (
                    "I couldn't find any relevant documents matching your query within "
                    "your accessible collections. Please try rephrasing your question."
                )
                logger.info("[PIPELINE] No chunks retrieved")
                return {"messages": [AIMessage(content=response.answer)], "response": response}
        else:
            # ─── Step 5: Context Building ─────────────────────────────────────────
            step_start = time.perf_counter()
            context = build_context(chunks)
            logger.debug(f"Step 5 completed in {time.perf_counter() - step_start:.3f}s")

        # ─── Step 6: LLM Generation ──────────────────────────────────────────
        step_start = time.perf_counter()
        logger.info("[PIPELINE] Step 6: LLM generation")

        answer = await generate_answer(query=query, context=context, chat_history=chat_history)
        response.answer = answer
        logger.debug(f"Step 6 completed in {time.perf_counter() - step_start:.3f}s")

        # ─── Step 7: Output Guardrails ────────────────────────────────────────
        step_start = time.perf_counter()
        logger.info("[PIPELINE] Step 7: Output guardrails")

        output_warnings = run_output_guardrails(answer, context, user.role)
        response.guardrail_warnings.extend(output_warnings)
        logger.debug(f"Step 7 completed in {time.perf_counter() - step_start:.3f}s")

        total_time = time.perf_counter() - start_time
        logger.info(
            f"[PIPELINE] Complete — route={route_name}, "
            f"chunks={len(chunks)}, time={total_time:.3f}s"
        )

        return {"messages": [AIMessage(content=response.answer)], "response": response}

    except Exception as e:
        logger.error(f"[PIPELINE] Critical failure: {e}", exc_info=True)
        response.answer = "An internal error occurred while processing your request. Please try again later."
        response.blocked = True
        response.blocked_reason = "internal_error"
        return {"messages": [AIMessage(content=response.answer)], "response": response}
        

# Build the Graph
workflow = StateGraph(PipelineState)
workflow.add_node("pipeline", pipeline_node)
workflow.add_edge(START, "pipeline")
workflow.add_edge("pipeline", END)


async def process_query(query: str, user: User, session_id: str) -> ChatResponse:
    """
    Process a user query through the full LangGraph RAG pipeline.
    Utilizes PostgreSQL checkpointer for conversational memory with Memory fallback.
    """
    settings = get_settings()
    
    # 1. Prepare Checkpointer URL - Use DIRECT (non-pooler) endpoint for stability
    # LangGraph checkpointer is often incompatible with Transaction-mode poolers.
    db_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    db_url = db_url.replace("-pooler.", ".").replace("&channel_binding=require", "").replace("?channel_binding=require", "")
    
    checkpointer_type = "postgres"
    
    try:
        # 2. Attempt Connection to Postgres Checkpointer
        async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
            # Note: We skip cp.setup() because tables were pre-created via Direct endpoint.
            # This Avoids Pooler DDL issues and speeds up the request.
            return await _execute_graph(query, user, session_id, checkpointer)
            
    except Exception as e:
        logger.warning(f"Postgres checkpointer connection failed [{type(e).__name__}]: {e}. Falling back to MemorySaver.")
        checkpointer_type = "memory"
        
        # 3. Fallback to MemorySaver for High-Availability
        checkpointer = MemorySaver()
        return await _execute_graph(query, user, session_id, checkpointer)


async def _execute_graph(query: str, user: User, session_id: str, checkpointer: Any) -> ChatResponse:
    """Helper to compile and invoke the graph with a specific checkpointer."""
    app = workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": session_id}}
    
    result = await app.ainvoke(
        {
            "messages": [HumanMessage(content=query)],
            "query": query,
            "user": user,
            "session_id": session_id
        },
        config=config
    )
    
    return result["response"]
