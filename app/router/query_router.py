"""
Semantic query router.

Classifies user queries into department routes and intersects
with user role for RBAC-aware routing.
"""
import re
import logging
from typing import Tuple, List, Optional
from semantic_router import SemanticRouter
from semantic_router.encoders import HuggingFaceEncoder
from semantic_router.index.qdrant import QdrantIndex
from app.config import get_settings
from app.router.routes import ALL_ROUTES
from app.rbac.access_control import check_route_access

logger = logging.getLogger(__name__)

class HybridQueryRouter:
    """
    Production-grade Hybrid Router.
    Combines Deterministic (Regex) with Semantic (Embeddings) routing.
    """
    def __init__(self):
        try:
            settings = get_settings()
            self.encoder = HuggingFaceEncoder(name=settings.EMBEDDING_MODEL_NAME)
            
            if settings.qdrant_is_cloud:
                self.index = QdrantIndex(
                    url=settings.QDRANT_HOST,
                    api_key=settings.QDRANT_API_KEY or None,
                    location=None,
                    collection_name=settings.QDRANT_COLLECTION_NAME_ROUTES
                )
            else:
                self.index = QdrantIndex(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                    location=None,
                    collection_name=settings.QDRANT_COLLECTION_NAME_ROUTES
                )
                
            self.router = SemanticRouter(
                encoder=self.encoder,
                routes=ALL_ROUTES,
                index=self.index,
                auto_sync="local"
            )
            logger.info("Semantic router layer initialized successfully")
        except Exception as e:
            logger.error(f"Router initialization failed: {e}")
            self.router = None

        # BROAD KEYWORD MAP (Highest Priority)
        self.keyword_map = {
            "marketing_route": [r"\bmarketing\b", r"\bcampaign\b", r"\battract\b", r"\bclient\b", r"\bsell\b", r"\bteam\b"],
            "finance_route":   [r"\bfinance\b", r"\brevenue\b", r"\bbudget\b", r"\bvendor\b", r"\bpayment\b", r"\bspend\b", r"\bcost\b"],
            "engineering_route": [r"\bengineering\b", r"\barchitecture\b", r"\bdeployment\b", r"\bapi\b", r"\bcode\b", r"\bsoftware\b"],
            "hr_general_route":  [r"\bleave\b", r"\bhandbook\b", r"\bhr\b", r"\bdress\scode\b", r"\bpolicy\b", r"\bholiday\b"]
        }

    def _get_deterministic_route(self, query: str) -> Optional[str]:
        """Layer 1: Fast Regex Matching."""
        q = query.lower().strip()
        for route, patterns in self.keyword_map.items():
            if any(re.search(p, q) for p in patterns):
                return route
        return None

    def route(self, query: str, user_role: str, extra_roles: Optional[List[str]] = None) -> Tuple[str, List[str], str]:
        """Full Routing Pipeline with RBAC."""
        try:
            # --- PHASE 1: Deterministic ---
            route_name = self._get_deterministic_route(query)
            
            # --- PHASE 2: Semantic (only if Phase 1 failed and router is initialized) ---
            if not route_name and self.router:
                result = self.router(query)
                if result and result.name:
                    route_name = result.name
            
            # Default fallback
            if not route_name:
                route_name = "cross_department_route"
            
            # --- PHASE 3: Admin Bypass for Off-Topic/Harmful ---
            # If Admin (c_level or extra c_level), we search anyway but keep the route name for metadata
            denial_message = ""
            if route_name == "off_topic" and (user_role != "c_level" and "c_level" not in (extra_roles or [])):
                denial_message = "Your query appears to be unrelated to FinSolve's business domains."
                return "off_topic", [], denial_message
            
            if route_name == "harmful":
                return "harmful", [], "Security violation detected."

            # --- PHASE 4: RBAC Enforcement ---
            is_allowed, collections, denial = check_route_access(user_role, route_name, extra_roles)
            return route_name, collections, denial

        except Exception as e:
            logger.error(f"Routing failed: {e}. Falling back to default search.")
            # Absolute safety fallback
            from app.rbac.access_control import get_accessible_collections
            return "cross_department_route", get_accessible_collections(user_role, extra_roles), ""

# Single Instance for entire app
_hybrid_router: Optional[HybridQueryRouter] = None

def route_query(query: str, user_role: str, extra_roles: Optional[List[str]] = None):
    global _hybrid_router
    try:
        if _hybrid_router is None:
            _hybrid_router = HybridQueryRouter()
        return _hybrid_router.route(query, user_role, extra_roles)
    except Exception as e:
        logger.error(f"Global route_query error: {e}")
        from app.rbac.access_control import get_accessible_collections
        return "cross_department_route", get_accessible_collections(user_role, extra_roles), ""
