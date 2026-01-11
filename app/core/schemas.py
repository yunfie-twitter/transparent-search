"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================================
# Click Event
# ============================================================================

class ClickEvent(BaseModel):
    """User click event for analytics."""
    query_id: int
    page_id: int


class ClickEventResponse(BaseModel):
    """Response for click event logging."""
    status: str
    click_id: Optional[str] = None
    timestamp: Optional[datetime] = None


# ============================================================================
# Search
# ============================================================================

class SearchRequest(BaseModel):
    """Search request schema."""
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(10, ge=1, le=100)
    offset: int = Field(0, ge=0)
    explain: bool = False


class SearchResult(BaseModel):
    """Individual search result."""
    id: int
    title: str
    url: str
    score: float
    domain: Optional[str] = None
    favicon: Optional[str] = None
    snippet: Optional[str] = None
    content_type: Optional[str] = None
    tracker_risk_score: Optional[float] = None


class SearchResponse(BaseModel):
    """Search response schema."""
    query: str
    count: int
    results: List[SearchResult]
    took_ms: int


# ============================================================================
# Admin/Crawl
# ============================================================================

class CrawlSessionRequest(BaseModel):
    """Request to start crawl session."""
    domain: str = Field(..., min_length=1)
    max_depth: int = Field(3, ge=1, le=15)
    enable_js_rendering: bool = False


class CrawlSessionResponse(BaseModel):
    """Crawl session details."""
    session_id: str
    domain: str
    status: str
    created_at: Optional[datetime] = None


class CrawlJobRequest(BaseModel):
    """Request to create crawl job."""
    session_id: str
    url: str = Field(..., min_length=5)
    depth: int = Field(0, ge=0, le=10)


class CrawlJobResponse(BaseModel):
    """Crawl job details."""
    job_id: str
    url: str
    status: str
    priority: Optional[int] = None
    page_value_score: Optional[float] = None


# ============================================================================
# Analysis Results
# ============================================================================

class MetadataAnalysisResult(BaseModel):
    """Metadata analysis result."""
    title: Optional[str] = None
    description: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    structured_data: Optional[dict] = None
    language: Optional[str] = None
    author: Optional[str] = None
    publish_date: Optional[str] = None
    update_date: Optional[str] = None


class PageValueScoreResult(BaseModel):
    """Page value scoring result."""
    url: str
    total_score: float = Field(..., ge=0, le=100)
    crawl_priority: int = Field(..., ge=1, le=10)
    recommendation: str  # CRAWL_NOW, CRAWL_SOON, CRAWL_LATER, LOW_VALUE
    breakdown: Optional[dict] = None


class SpamDetectionResult(BaseModel):
    """Spam detection result."""
    domain: str
    spam_score: float = Field(..., ge=0, le=100)
    risk_level: str  # clean, suspicious, spam
    signals: List[str] = []
    is_safe: bool


class QueryIntentResult(BaseModel):
    """Query intent analysis result."""
    query: str
    primary_intent: str
    confidence: float = Field(..., ge=0, le=1)
    intent_scores: Optional[dict] = None
    expertise_level: Optional[str] = None


# ============================================================================
# Error Response
# ============================================================================

class ErrorResponse(BaseModel):
    """Error response schema."""
    status: str = "error"
    detail: str
    error_code: Optional[str] = None
    timestamp: Optional[datetime] = None
