"""
Pydantic request and response models for the MemoryAI API.

All models are centralized here per Requirement 1.5 and 9.1.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Request models (extracted from main.py)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class MemoryCreate(BaseModel):
    diary_date: str
    diary_time: Optional[str] = None
    timezone: Optional[str] = None
    topic: str
    summary: str
    emotion_score: int
    keywords: List[str]
    original_text: Optional[str] = ""
    content: Optional[str] = ""
    importance_weight: Optional[int] = 3


class MemoryUpdate(BaseModel):
    diary_date: Optional[str] = None
    diary_time: Optional[str] = None
    timezone: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    emotion_score: Optional[int] = None
    keywords: Optional[List[str]] = None
    original_text: Optional[str] = None


class ImportSingleRequest(BaseModel):
    date_str: str
    content: str


# ---------------------------------------------------------------------------
# Response models (new — used by refactored route handlers)
# ---------------------------------------------------------------------------

class MemoryResponse(BaseModel):
    id: str
    user_id: str
    diary_date: str
    diary_time: Optional[str]
    timezone: Optional[str]
    topic: str
    summary: str
    emotion_score: int
    keywords: List[str]
    content: Optional[str]
    created_at: str
    deleted_at: Optional[str] = None


class SummarizedEvent(BaseModel):
    """
    Represents a single diary event extracted and summarized by the AI.

    Requirements 1.5 and 9.1: importance_weight is constrained to [1, 5].
    """
    summary: str
    topic: str
    keywords: List[str]
    emotion_score: int = Field(ge=0, le=100)
    importance_weight: int = Field(ge=1, le=5)
    diary_date: str
    diary_time: str
    timezone: Optional[str] = "Asia/Taipei"


class ContextUpdate(BaseModel):
    """Represents an AI-generated update to the user's rolling context narrative."""
    __context_update__: str


class EntityProfile(BaseModel):
    """A core person or object extracted from memories."""
    name: str
    relationship: str
    description: str
    is_person: bool = True


class ParseError(BaseModel):
    """
    Structured error returned when AI JSON parsing fails at any tier.

    Categories:
    - ``parse_error``              — all JSON parsing attempts failed
    - ``schema_validation_error`` — JSON parsed but Pydantic validation failed
    - ``retry_error``              — 503 retries exhausted
    - ``provider_error``           — non-503 HTTP error from AI provider
    """
    category: str  # "parse_error" | "schema_validation_error" | "retry_error" | "provider_error"
    message: str
    raw_response: Optional[str] = None  # Truncated to 10 000 chars


class ChatResponse(BaseModel):
    reply: str


class SummarizeResponse(BaseModel):
    success: bool
    events: List[SummarizedEvent]


class DashboardStats(BaseModel):
    emotion_trends: List[dict]
    keyword_distribution: List[dict]
    summary_stats: Optional[dict] = None
    entity_analysis: Optional[List[dict]] = None


class GraphData(BaseModel):
    nodes: List[dict]
    links: List[dict]
