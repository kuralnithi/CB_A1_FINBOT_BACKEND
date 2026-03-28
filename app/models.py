"""Pydantic models and schemas for FinBot."""
from __future__ import annotations
import uuid
from typing import Optional
from pydantic import BaseModel, Field


# ─── User & Auth ───────────────────────────────────────────────────────────────

class User(BaseModel):
    """User model with role-based access."""
    username: str
    role: str
    display_name: str = ""
    extra_roles: list[str] = Field(default_factory=list)

class UserCreate(BaseModel):
    """Schema for creating a new user."""
    username: str
    password: str
    role: str
    display_name: str = ""

class LoginRequest(BaseModel):
    username: str
    password: str = ""  # Demo mode: password not enforced


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User


# ─── Chunk Metadata ────────────────────────────────────────────────────────────

class ChunkMetadata(BaseModel):
    """Metadata attached to every indexed chunk."""
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_document: str
    collection: str  # finance | engineering | marketing | general
    access_roles: list[str]  # roles that can access this chunk
    section_title: str = ""
    page_number: int = 0
    chunk_type: str = "text"  # text | table | code | heading
    parent_chunk_id: Optional[str] = None
    hierarchy_path: list[str] = Field(default_factory=list)
    parent_summary: str = ""


# ─── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class SourceCitation(BaseModel):
    document: str
    page_number: int = 0
    section: str = ""
    chunk_type: str = "text"
    relevance_score: float = 0.0


class GuardrailWarning(BaseModel):
    type: str  # injection | off_topic | pii | rate_limit | grounding | leakage | citation
    message: str
    severity: str = "warning"  # warning | error | info


class ChatResponse(BaseModel):
    answer: str = ""
    sources: list[SourceCitation] = Field(default_factory=list)
    route_selected: str = ""
    user_role: str = ""
    accessible_collections: list[str] = Field(default_factory=list)
    guardrail_warnings: list[GuardrailWarning] = Field(default_factory=list)
    blocked: bool = False
    blocked_reason: str = ""


# ─── Admin ─────────────────────────────────────────────────────────────────────

class DocumentInfo(BaseModel):
    filename: str
    collection: str
    chunk_count: int = 0
    status: str = "indexed"


class IngestResponse(BaseModel):
    status: str
    documents_processed: int = 0
    chunks_created: int = 0
    message: str = ""
