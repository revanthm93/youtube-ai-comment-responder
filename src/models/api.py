"""
Pydantic models for API request/response schemas.
"""

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

from src.models.youtube import (
    CommentBatch,
    ProcessedComment,
    ProcessingStatus,
    QuotaUsage,
    VideoInfo,
)


# Generic type for paginated responses
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""

    items: List[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total count")
    page: int = Field(default=1, description="Current page")
    page_size: int = Field(default=50, description="Items per page")
    has_next: bool = Field(default=False, description="Has next page")
    has_previous: bool = Field(default=False, description="Has previous page")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    success: bool = Field(..., description="Whether request succeeded")
    data: Optional[T] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Human-readable message")
    error: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    components: Dict[str, str] = Field(default_factory=dict, description="Component statuses")


# ============================================================================
# Comment Endpoints
# ============================================================================


class FetchCommentsRequest(BaseModel):
    """Request to fetch comments."""

    video_id: Optional[str] = Field(None, description="Specific video ID (optional)")
    max_results: int = Field(default=50, ge=1, le=100, description="Max comments to fetch")
    include_replies: bool = Field(default=False, description="Include reply threads")
    only_unanswered: bool = Field(default=True, description="Only fetch unanswered comments")


class FetchCommentsResponse(BaseModel):
    """Response from fetching comments."""

    batch_id: str = Field(..., description="Batch ID for tracking")
    comments_fetched: int = Field(..., description="Number of comments fetched")
    video_ids: List[str] = Field(..., description="Video IDs included")
    next_page_token: Optional[str] = Field(None, description="Token for pagination")


class ProcessCommentsRequest(BaseModel):
    """Request to process comments."""

    batch_id: Optional[str] = Field(None, description="Process specific batch")
    video_id: Optional[str] = Field(None, description="Process video's comments")
    comment_ids: Optional[List[str]] = Field(None, description="Process specific comments")
    dry_run: bool = Field(default=True, description="Don't actually post replies")


class ProcessCommentsResponse(BaseModel):
    """Response from processing comments."""

    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status")
    comments_queued: int = Field(..., description="Comments queued for processing")


class CommentStatusRequest(BaseModel):
    """Request to get comment status."""

    comment_ids: List[str] = Field(..., description="Comment IDs to check")


class CommentStatusResponse(BaseModel):
    """Response with comment statuses."""

    statuses: Dict[str, ProcessingStatus] = Field(..., description="Status by comment ID")


# ============================================================================
# Response Generation
# ============================================================================


class GenerateResponseRequest(BaseModel):
    """Request to generate a response for a comment."""

    comment_text: str = Field(..., min_length=1, description="Comment text")
    video_id: Optional[str] = Field(None, description="Video ID for context")
    author_name: Optional[str] = Field(None, description="Commenter's name")
    force_tier: Optional[str] = Field(None, description="Force specific tier")


class GenerateResponseResponse(BaseModel):
    """Response with generated reply."""

    response_text: str = Field(..., description="Generated response")
    tier_used: str = Field(..., description="Response tier used")
    classification: Dict[str, Any] = Field(..., description="Comment classification")
    rag_context: Optional[List[str]] = Field(None, description="RAG context used")
    processing_time_ms: float = Field(..., description="Processing time")


class PostReplyRequest(BaseModel):
    """Request to post a reply."""

    comment_id: str = Field(..., description="Comment ID to reply to")
    response_text: str = Field(..., min_length=1, description="Reply text")
    skip_moderation: bool = Field(default=False, description="Skip content moderation")


class PostReplyResponse(BaseModel):
    """Response from posting a reply."""

    success: bool = Field(..., description="Whether reply was posted")
    reply_id: Optional[str] = Field(None, description="ID of posted reply")
    moderation_passed: bool = Field(default=True, description="Passed moderation")
    moderation_issues: Optional[List[str]] = Field(None, description="Moderation issues")


# ============================================================================
# Video & Transcript
# ============================================================================


class VideoListResponse(BaseModel):
    """Response with list of videos."""

    videos: List[VideoInfo] = Field(..., description="Video list")
    total: int = Field(..., description="Total videos")


class IndexVideoRequest(BaseModel):
    """Request to index a video's transcript."""

    video_id: str = Field(..., description="Video ID to index")
    force_reindex: bool = Field(default=False, description="Force re-indexing")


class IndexVideoResponse(BaseModel):
    """Response from indexing video."""

    video_id: str = Field(..., description="Video ID")
    success: bool = Field(..., description="Whether indexing succeeded")
    chunks_indexed: int = Field(default=0, description="Number of chunks indexed")
    transcript_language: Optional[str] = Field(None, description="Transcript language")
    error: Optional[str] = Field(None, description="Error message if failed")


# ============================================================================
# Quota & Stats
# ============================================================================


class QuotaStatusResponse(BaseModel):
    """Response with quota status."""

    quota: QuotaUsage = Field(..., description="Current quota usage")
    can_read: bool = Field(..., description="Can perform read operations")
    can_write: bool = Field(..., description="Can perform write operations")
    estimated_remaining_replies: int = Field(..., description="Estimated replies possible")


class StatsResponse(BaseModel):
    """Response with system statistics."""

    total_comments_processed: int = Field(default=0)
    total_replies_posted: int = Field(default=0)
    responses_by_tier: Dict[str, int] = Field(default_factory=dict)
    average_response_time_ms: float = Field(default=0.0)
    success_rate: float = Field(default=0.0)
    quota_usage_today: int = Field(default=0)
    period_start: datetime = Field(...)
    period_end: datetime = Field(...)


# ============================================================================
# Task Status
# ============================================================================


class TaskStatusResponse(BaseModel):
    """Response with Celery task status."""

    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status")
    progress: Optional[float] = Field(None, description="Progress percentage")
    result: Optional[Dict[str, Any]] = Field(None, description="Task result")
    error: Optional[str] = Field(None, description="Error if failed")
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)