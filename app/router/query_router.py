"""
Semantic query router.

Classifies user queries into department routes and intersects
with user role for RBAC-aware routing.
"""
import re
import logging
from semantic_router import SemanticRouter
from semantic_router.encoders import HuggingFaceEncoder
from semantic_router.index.qdrant import QdrantIndex
from app.config import get_settings

from app.router.routes import ALL_ROUTES
from app.rbac.access_control import check_route_access

logger = logging.getLogger(__name__)

# Module-level cache for the router
_route_layer: SemanticRouter | None = None

# ─── Keyword-based route override ─────────────────────────────────────────────
# If a query explicitly mentions a department name, we override the semantic
# router's result to ensure RBAC is correctly enforced. This prevents
# misrouting like "tell me about marketing details" → hr_general_route.
KEYWORD_ROUTE_MAP = {
    r"\bmarketing\b": "marketing_route",
    r"\bfinance\b|\bfinancial\b|\brevenue\b|\bbudget\b": "finance_route",
    r"\bengineering\b|\barchitecture\b|\bdeployment\b|\bincident\b|\bci/cd\b|\bsla\b": "engineering_route",
    r"\bleave\s+policy\b|\bhandbook\b|\bhr\b|\bhuman\s+resource\b|\bdress\s+code\b|\bworking\s+hours\b": "hr_general_route",
}


def _keyword_override(query: str, semantic_route: str) -> str:
    """
    If the query explicitly mentions a department keyword, override the
    semantic router result to ensure the correct route (and thus RBAC
    enforcement) is applied.

    Only overrides when the semantic route does NOT already match the keyword.
    """
    query_lower = query.lower().strip()

    for pattern, route_name in KEYWORD_ROUTE_MAP.items():
        if re.search(pattern, query_lower):
            if semantic_route != route_name:
                logger.info(
                    f"Keyword override: '{semantic_route}' → '{route_name}' "
                    f"(matched pattern: {pattern})"
                )
            return route_name

    return semantic_route


def get_route_layer() -> SemanticRouter:
    """Get or create the semantic route layer (cached)."""
    global _route_layer
    settings = get_settings()


    if _route_layer is None:
        logger.info("Initializing semantic router with HuggingFace encoder...")
        encoder = HuggingFaceEncoder(name="BAAI/bge-small-en-v1.5")
        # Connect the Router's index to your Qdrant instance
        # NOTE: Use a different collection name than your documents!
        index = QdrantIndex(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            location=None, # This is the critical missing piece
            collection_name=settings.QDRANT_COLLECTION_NAME_ROUTES
        )
        _route_layer = SemanticRouter(
            encoder=encoder,
            routes=ALL_ROUTES,
            index=index,
            auto_sync="local"
        )
        logger.info("Semantic router initialized successfully")
    return _route_layer


def route_query(query: str, user_role: str, extra_roles: list[str] | None = None) -> tuple[str, list[str], str]:
    """
    Route a query and intersect with user's role for RBAC.

    Args:
        query: User's query string
        user_role: User's role (e.g., 'finance', 'engineering')
        extra_roles: Any additional roles granted to the user.

    Returns:
        (route_name, target_collections, denial_message)
        - If route is allowed: (route_name, [collections], "")
        - If route is denied: (route_name, [], denial_message)
    """
    router = get_route_layer()

    # Classify the query via semantic router
    route_result = router(query)
    route_name = route_result.name if route_result and route_result.name else "cross_department_route"

    # Explicitly block off-topic or harmful routes from the semantic router
    if route_name == "off_topic":
        return "off_topic", [], "Your query appears to be unrelated to FinSolve's business domains. I can only help with questions about company policies, finance, engineering, or marketing."
    
    if route_name == "harmful":
        return "harmful", [], "Your query appears to contain harmful content or a prompt injection attempt. This request has been blocked for security reasons."

    # Apply keyword-based correction to fix semantic router misclassifications
    route_name = _keyword_override(query, route_name)

    logger.info(f"Query routed to: {route_name} (user_role={user_role})")

    # Intersect with role access
    is_allowed, collections, denial_message = check_route_access(user_role, route_name, extra_roles)

    if not is_allowed:
        logger.warning(
            f"Route access DENIED: role='{user_role}', route='{route_name}', "
            f"message='{denial_message}'"
        )

    return route_name, collections, denial_message
