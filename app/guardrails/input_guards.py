"""
Input guardrails — validates user queries before processing.

Guards against:
- Prompt injection attacks
- Off-topic queries
- PII in queries
- Rate limiting (20 queries/session)
"""
import re
import logging
from collections import defaultdict

from app.models import GuardrailWarning

logger = logging.getLogger(__name__)

# ─── In-memory rate limiter ────────────────────────────────────────────────────
_session_counters: dict[str, int] = defaultdict(int)
MAX_QUERIES_PER_SESSION = 20


def reset_session(session_id: str):
    """Reset rate limit counter for a session."""
    _session_counters.pop(session_id, None)


# ─── Prompt Injection Detection ────────────────────────────────────────────────

INJECTION_PATTERNS = [
    r"ignore\s+(your|all|previous|prior)\s+(instructions|rules|constraints|prompt)",
    r"act\s+as\s+(a\s+)?different\s+assistant",
    r"(override|bypass|disable|ignore)\s+(rbac|access\s+control|restrictions|permissions|security)",
    r"show\s+me\s+(all|every)\s+documents?\s+(regardless|irrespective)",
    r"forget\s+(everything|your\s+training|your\s+instructions)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"pretend\s+(you\s+are|to\s+be)",
    r"new\s+instruction[s]?\s*:",
    r"system\s*prompt\s*:",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"no\s+restrictions",
    r"reveal\s+(your|the)\s+(system|hidden)\s+prompt",
]

MALICIOUS_PATTERNS = [
    r"(how\s+to\s+)?(hack|crack|bypass|exploit|penetrate|ddos|phish)",
    r"run\s+(a\s+)?(script|command|code)",
    r"extract\s+(all\s+)?(data|users|passwords)",
]


def detect_prompt_injection(query: str) -> GuardrailWarning | None:
    """Detect prompt injection attempts using regex patterns."""
    query_lower = query.lower().strip()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, query_lower):
            logger.warning(f"GUARDRAIL: Prompt injection detected — pattern: {pattern}")
            return GuardrailWarning(
                type="injection",
                message="Your query appears to contain a prompt injection attempt. "
                        "This request has been blocked for security reasons.",
                severity="error",
            )
    return None


def detect_malicious_intent(query: str) -> GuardrailWarning | None:
    """Detect malicious queries that should be blocked (hacking, etc.)."""
    query_lower = query.lower().strip()

    for pattern in MALICIOUS_PATTERNS:
        if re.search(pattern, query_lower):
            logger.warning(f"GUARDRAIL: Malicious intent detected — pattern: {pattern}")
            return GuardrailWarning(
                type="malicious",
                message="Your query contains prohibited content related to hacking or system exploitation. "
                        "This request has been blocked and logged for security review.",
                severity="error",
            )
    return None


# ─── Off-Topic Detection ──────────────────────────────────────────────────────

OFF_TOPIC_PATTERNS = [
    r"(write|compose|create)\s+(me\s+)?(a\s+)?(poem|story|song|joke|essay)",
    r"(what.s|tell\s+me)\s+(the\s+)?(cricket|football|sports?|weather|movie|game)\s+(score|result|forecast)",
    r"(play|tell)\s+(me\s+)?(a\s+)?(game|riddle|trivia)",
    r"(translate|convert)\s+.{0,30}\s+(to|into)\s+(french|spanish|german|hindi|chinese)",
    r"(recipe|cook|bake)\s+(for|me)",
    r"(who\s+won|who\s+is\s+the)\s+(the\s+)?(election|president|championship|world\s+cup)",
    r"(help\s+me\s+with\s+)?(my\s+)?(homework|assignment|exam)",
    r"(what\s+is\s+the\s+meaning\s+of\s+life|tell\s+me\s+a\s+joke|sing\s+a\s+song)",
]

BUSINESS_KEYWORDS = [
    "finsolve", "company", "employee", "policy", "leave", "handbook",
    "financial", "finance", "revenue", "budget", "report", "quarterly", "annual",
    "engineering", "architecture", "api", "system", "deployment", "incident",
    "marketing", "campaign", "brand", "customer", "competitor",
    "hr", "benefit", "salary", "performance", "onboarding",
    "document", "department", "team", "business", "corporate", "general",
]


def detect_off_topic(query: str) -> GuardrailWarning | None:
    """Check if query is unrelated to FinSolve business domains."""
    query_lower = query.lower().strip()

    # Check explicit off-topic patterns
    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, query_lower):
            logger.warning(f"GUARDRAIL: Off-topic query detected — pattern: {pattern}")
            return GuardrailWarning(
                type="off_topic",
                message="Your query appears to be unrelated to FinSolve's business domains. "
                        "I can only help with questions about company policies, finance, "
                        "engineering, or marketing.",
                severity="warning",
            )

    # Check if any business keyword is present (simple heuristic)
    has_business_context = any(kw in query_lower for kw in BUSINESS_KEYWORDS)

    # Allow very short queries without triggering strict heuristic
    if len(query_lower.split()) < 3 and not has_business_context:
        return None  

    # Stricter heuristic: if it's not explicitly blocked but also has NO business context,
    # and it's longer than 3 words, we flag it as off-topic.
    if not has_business_context:
        logger.warning(f"GUARDRAIL: Query lacks business context: {query}")
        return GuardrailWarning(
            type="off_topic",
            message="Your query does not appear to be related to FinSolve documentation. "
                    "I am specialized in answering questions about FinSolve's internal operations, "
                    "engineering, finance, and marketing.",
            severity="warning",
        )

    return None


# ─── PII Detection ────────────────────────────────────────────────────────────

PII_PATTERNS = {
    "aadhaar": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b",
    "bank_account": r"\b\d{9,18}\b",  # Generic bank account pattern
    "pan": r"\b[A-Z]{5}\d{4}[A-Z]\b",
    "credit_card": r"\b(?:\d{4}[\s-]?){4}\b",
}


def detect_pii(query: str) -> GuardrailWarning | None:
    """Detect if user submitted personal identifiable information."""
    for pii_type, pattern in PII_PATTERNS.items():
        if re.search(pattern, query):
            logger.warning(f"GUARDRAIL: PII detected — type: {pii_type}")
            return GuardrailWarning(
                type="pii",
                message=f"Your query appears to contain personal information ({pii_type}). "
                        "Please remove any sensitive data before submitting.",
                severity="error",
            )
    return None


# ─── Rate Limiting ─────────────────────────────────────────────────────────────

def check_rate_limit(session_id: str) -> GuardrailWarning | None:
    """Check if session has exceeded the query limit."""
    _session_counters[session_id] += 1
    count = _session_counters[session_id]

    if count > MAX_QUERIES_PER_SESSION:
        logger.warning(f"GUARDRAIL: Rate limit exceeded — session: {session_id}, count: {count}")
        return GuardrailWarning(
            type="rate_limit",
            message=f"You have exceeded the maximum of {MAX_QUERIES_PER_SESSION} queries per session. "
                    "Please start a new session to continue.",
            severity="error",
        )
    return None


# ─── Orchestrator ──────────────────────────────────────────────────────────────

def run_input_guardrails(query: str, session_id: str) -> list[GuardrailWarning]:
    """
    Run all input guardrail checks.

    Returns list of warnings. If any have severity='error', the query should be blocked.
    """
    warnings: list[GuardrailWarning] = []

    # Rate limit
    rate_warning = check_rate_limit(session_id)
    if rate_warning:
        warnings.append(rate_warning)
        return warnings  # Block immediately

    # Prompt injection
    injection_warning = detect_prompt_injection(query)
    if injection_warning:
        warnings.append(injection_warning)
        return warnings  # Block immediately

    # Malicious intent (hacking, etc.)
    malicious_warning = detect_malicious_intent(query)
    if malicious_warning:
        warnings.append(malicious_warning)
        return warnings  # Block immediately

    # PII
    pii_warning = detect_pii(query)
    if pii_warning:
        warnings.append(pii_warning)
        return warnings  # Block immediately

    # Off-topic
    offtopic_warning = detect_off_topic(query)
    if offtopic_warning:
        warnings.append(offtopic_warning)
        return warnings  # Block immediately

    return warnings
