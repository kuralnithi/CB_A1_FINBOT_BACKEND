"""
Output guardrails — validates LLM responses before returning to user.

Guards against:
- Ungrounded claims (hallucination detection)
- Missing source citations
- Cross-role information leakage
"""
import re
import logging

from app.models import GuardrailWarning
from app.rbac.access_control import ROLE_ACCESS_MAP

logger = logging.getLogger(__name__)

# Collection-specific keywords for leakage detection
COLLECTION_KEYWORDS = {
    "finance": [
        "revenue", "budget", "profit", "loss", "earnings", "fiscal",
        "investor", "dividend", "quarterly financials", "operating expense",
        "financial projection", "P&L", "balance sheet", "cash flow",
    ],
    "engineering": [
        "architecture", "API endpoint", "microservice", "deployment pipeline",
        "CI/CD", "incident runbook", "sprint velocity", "SLA", "uptime",
        "system design", "code review", "pull request", "infrastructure",
    ],
    "marketing": [
        "campaign performance", "customer acquisition", "brand guideline",
        "market share", "competitor analysis", "digital advertising",
        "conversion rate", "marketing ROI", "content strategy",
        "social media engagement", "email campaign", "lead generation",
    ],
}


def check_grounding(response: str, context: str) -> GuardrailWarning | None:
    """
    Check if the LLM response is grounded in retrieved context.

    Looks for specific claims (numbers, dates, percentages) in the response
    and checks if they appear in the context.
    """
    # Extract numbers & percentages from response
    response_claims = set(re.findall(r'\b\d+(?:\.\d+)?(?:%|percent)?\b', response))

    if not response_claims:
        return None

    combined_context = context.lower()

    # Check if claims appear in context
    ungrounded_claims = []
    for claim in response_claims:
        # Skip very small numbers (1, 2, 3 etc.) as they're too generic
        try:
            num = float(claim.replace("%", "").replace("percent", ""))
            if num < 10:
                continue
        except ValueError:
            pass

        if claim.lower() not in combined_context:
            ungrounded_claims.append(claim)

    if len(ungrounded_claims) > 2:
        logger.warning(f"GUARDRAIL: Potentially ungrounded claims: {ungrounded_claims}")
        return GuardrailWarning(
            type="grounding",
            message="⚠️ This response may contain information not directly traceable to "
                    "the source documents. Please verify critical figures independently.",
            severity="warning",
        )

    return None


def check_citation_presence(response: str) -> GuardrailWarning | None:
    """
    Check if the response cites at least one source document.

    Looks for patterns like: "Source: document.pdf", "[document.pdf]",
    "page X", "(Source:", etc.
    """
    citation_patterns = [
        r"source[s]?\s*:",
        r"\[.*\.\w{2,4}.*\]",
        r"page\s+\d+",
        r"\(.*\.\w{2,4}.*\)",
        r"document\s*:",
        r"\*{0,2}References\*{0,2}",
        r"📄",
    ]

    for pattern in citation_patterns:
        if re.search(pattern, response, re.IGNORECASE):
            return None

    logger.warning("GUARDRAIL: No source citation found in response")
    return GuardrailWarning(
        type="citation",
        message="⚠️ This response does not explicitly cite source documents. "
                "Please check the source references below for verification.",
        severity="info",
    )


def check_cross_role_leakage(response: str, user_role: str) -> GuardrailWarning | None:
    """
    Check if the response contains terms from collections the user cannot access.

    E.g., an engineering user getting budget figures from finance docs.
    """
    accessible_collections = ROLE_ACCESS_MAP.get(user_role, [])

    # c_level can see everything
    if user_role == "c_level":
        return None

    response_lower = response.lower()
    leakage_detected = []

    for collection, keywords in COLLECTION_KEYWORDS.items():
        if collection in accessible_collections:
            continue  # User has access to this collection

        # Check for significant keyword matches
        matches = sum(1 for kw in keywords if kw.lower() in response_lower)
        if matches >= 3:
            leakage_detected.append(collection)

    if leakage_detected:
        logger.warning(
            f"GUARDRAIL: Potential cross-role leakage detected — "
            f"role='{user_role}', leaking from: {leakage_detected}"
        )
        return GuardrailWarning(
            type="leakage",
            message="⚠️ This response may contain information outside your authorized "
                    "access scope. The content has been flagged for review.",
            severity="warning",
        )

    return None


def run_output_guardrails(
    response: str,
    context: str,
    user_role: str,
) -> list[GuardrailWarning]:
    """
    Run all output guardrail checks.

    Returns list of warnings to append to the response.
    """
    warnings: list[GuardrailWarning] = []

    # Grounding check
    grounding_warning = check_grounding(response, context)
    if grounding_warning:
        warnings.append(grounding_warning)

    # Citation enforcement
    citation_warning = check_citation_presence(response)
    if citation_warning:
        warnings.append(citation_warning)

    # Cross-role leakage
    leakage_warning = check_cross_role_leakage(response, user_role)
    if leakage_warning:
        warnings.append(leakage_warning)

    return warnings
