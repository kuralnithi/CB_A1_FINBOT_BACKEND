"""
RBAC (Role-Based Access Control) module.

Enforces access control at the Qdrant vector DB query level.
CRITICAL: Unauthorized chunks are NEVER retrieved — filtering happens
in the Qdrant query, not in post-processing.
"""
import logging
from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue

logger = logging.getLogger(__name__)

# ─── Role → Collections Access Matrix ──────────────────────────────────────────
# Mirrors the assignment's access table exactly.

ROLE_ACCESS_MAP: dict[str, list[str]] = {
    "employee":    ["general"],
    "finance":     ["finance", "general"],
    "engineering": ["engineering", "general"],
    "marketing":   ["marketing", "general"],
    "c_level":     ["finance", "engineering", "marketing", "general"],
}

# Route → required collection mapping
ROUTE_COLLECTION_MAP: dict[str, list[str] | None] = {
    "finance_route":          ["finance"],
    "engineering_route":      ["engineering"],
    "marketing_route":        ["marketing"],
    "hr_general_route":       ["general"],
    "cross_department_route": None,  # None = search all accessible collections
    "greetings_route":        None,
    "off_topic":              None,
    "harmful":                None,
}

# Demo users with pre-defined roles
DEMO_USERS: dict[str, dict] = {
    "employee":    {"username": "employee",    "role": "employee",    "display_name": "Alex Employee"},
    "finance":     {"username": "finance",     "role": "finance",     "display_name": "Jordan Finance"},
    "engineering": {"username": "engineering", "role": "engineering", "display_name": "Sam Engineer"},
    "marketing":   {"username": "marketing",   "role": "marketing",  "display_name": "Taylor Marketing"},
    "c_level":     {"username": "c_level",     "role": "c_level",    "display_name": "Morgan CEO"},
}


def get_accessible_collections(role: str, extra_roles: list[str] | None = None) -> list[str]:
    """Return the deduplicated union of collections accessible by base role + any extra granted roles."""
    base = ROLE_ACCESS_MAP.get(role, [])
    if not base:
        logger.warning(f"Unknown role '{role}' — no base collections accessible")

    result = set(base)
    for extra in (extra_roles or []):
        result.update(ROLE_ACCESS_MAP.get(extra, []))

    return sorted(result)  # stable order


def check_route_access(role: str, route_name: str, extra_roles: list[str] | None = None) -> tuple[bool, list[str], str]:
    """
    Check if a user's role (+ any extra granted roles) grants access to the route's target collections.

    Returns:
        (allowed, target_collections, denial_message)
    """
    accessible = get_accessible_collections(role, extra_roles)
    required = ROUTE_COLLECTION_MAP.get(route_name)

    # cross_department_route or unknown route → search all accessible
    if required is None:
        logger.info(f"Role '{role}' using cross-department route → collections: {accessible}")
        return True, accessible, ""

    # Intersect required collections with accessible collections
    allowed_collections = [c for c in required if c in accessible]

    if not allowed_collections:
        message = (
            f"You do not have access to {route_name.replace('_route', '')} documents. "
            f"Your combined access: {', '.join(accessible)}."
        )
        logger.warning(f"RBAC DENIED: role='{role}', extra={extra_roles}, route='{route_name}', required={required}")
        return False, [], message

    logger.info(f"RBAC ALLOWED: role='{role}', extra={extra_roles}, route='{route_name}', collections={allowed_collections}")
    return True, allowed_collections, ""


def build_qdrant_filter(role: str, target_collections: list[str] | None = None, extra_roles: list[str] | None = None) -> Filter:
    """
    Build a Qdrant metadata filter that enforces RBAC.

    This filter is applied AT QUERY TIME in Qdrant so unauthorized
    chunks are never retrieved.

    Args:
        role: The user's primary role
        target_collections: Specific collections to search (from router).
                           If None, uses all accessible collections.
        extra_roles: Additional roles granted to the user by an admin.

    Returns:
        Qdrant Filter object
    """
    accessible = get_accessible_collections(role, extra_roles)

    # All roles the user can act as — for the access_roles metadata filter
    all_roles = list({role} | set(extra_roles or []))

    if target_collections:
        # Intersect with accessible — safety net
        collections_to_search = [c for c in target_collections if c in accessible]
    else:
        collections_to_search = accessible

    # SUPER ADMIN BYPASS: If c_level, search everything (no filters)
    if role == "c_level":
        logger.info(f"Super Admin bypass: Searching all collections for {role}")
        return None

    # Build the filter for all other roles
    must_conditions = [
        FieldCondition(
            key="collection",
            match=MatchAny(any=collections_to_search),
        )
    ]
    
    # Check for access_roles metadata
    must_conditions.append(
        FieldCondition(
            key="access_roles",
            match=MatchAny(any=all_roles),
        )
    )

    qdrant_filter = Filter(must=must_conditions)

    logger.info(
        f"Built Qdrant filter: role='{role}', extra={extra_roles}, "
        f"collections={collections_to_search}"
    )
    return qdrant_filter
