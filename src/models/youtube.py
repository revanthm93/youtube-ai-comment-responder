"""
Pydantic models for YouTube data structures.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class CommentType(str, Enum):
    """Classification of comment types for routing."""

    SIMPLE = "simple"  # Tier 1: Thanks, emoji, short praise
    QUESTION = "question"  # Tier 2: Questions about content
    COMPLEX = "complex"  # Tier 3: Detailed questions, multi-part
    SPAM = "spam"  # Skip: Spam or promotional content
    NEGATIVE = "negative"  # Requires careful handling


class Sentiment(str, Enum):
    """Sentiment classification."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class ResponseTier(str, Enum):
    """Response generation tier."""

    TIER_1_TEMPLATE = "tier_1_template"
    TIER_2_RAG = "tier_2_rag"
    TIER_3_LLM = "tier_3_llm"


class ProcessingStatus(str, Enum):
    """Comment processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    RESPONDED = "responded"
    SKIPPED = "skipped"
    FAILED = "failed"
    MODERATED = "moderated"


class YouTubeAuthor(BaseModel):
    """YouTube comment author information."""

    channel_id: str = Field(..., description="Author's channel ID")
    channel_url: str = Field(..., description="Author's channel URL")
    display_name: str = Field(..., description="Author's display name")
    profile_image_url: Optional[str] = Field(None, description="Profile image URL")


class YouTubeComment(BaseModel):
    """YouTube comment data model."""

    comment_id: str = Field(..., description="Unique comment ID")
    video_id: str = Field(..., description="Video ID the comment belongs to")
    text: str = Field(..., description="Comment text content")
    author: YouTubeAuthor = Field(..., description="Comment author info")
    published_at: datetime = Field(..., description="When comment was posted")
    updated_at: Optional[datetime] = Field(None, description="When comment was updated")
    like_count: int = Field(default=0, description="Number of likes")
    reply_count: int = Field(default=0, description="Number of replies")
    parent_id: Optional[str] = Field(None, description="Parent comment ID if this is a reply")
    is_reply: bool = Field(default=False, description="Whether this is a reply")

    @field_validator("text")
    @classmethod
    def clean_text(cls, v: str) -> str:
        """Clean and normalize comment text."""
        return v.strip()


class CommentClassification(BaseModel):
    """Result of comment classification."""

    comment_type: CommentType = Field(..., description="Classified comment type")
    sentiment: Sentiment = Field(..., description="Detected sentiment")
    response_tier: ResponseTier = Field(..., description="Recommended response tier")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    topics: List[str] = Field(default_factory=list, description="Detected topics")
    language: str = Field(default="unknown", description="Detected language")
    requires_moderation: bool = Field(default=False, description="Needs human review")
    skip_reason: Optional[str] = Field(None, description="Reason if skipping response")


class GeneratedResponse(BaseModel):
    """Generated response for a comment."""

    response_text: str = Field(..., description="Generated response text")
    tier_used: ResponseTier = Field(..., description="Response tier that was used")
    model_used: Optional[str] = Field(None, description="LLM model used if applicable")
    rag_context_used: bool = Field(default=False, description="Whether RAG context was used")
    retrieved_chunks: List[str] = Field(default_factory=list, description="RAG chunks used")
    generation_time_ms: float = Field(..., description="Time to generate response")
    token_count: Optional[int] = Field(None, description="Tokens used")
    cost_estimate: Optional[float] = Field(None, description="Estimated cost in USD")


class ProcessedComment(BaseModel):
    """A comment with its processing results."""

    comment: YouTubeComment = Field(..., description="Original comment")
    classification: CommentClassification = Field(..., description="Classification result")
    response: Optional[GeneratedResponse] = Field(None, description="Generated response")
    status: ProcessingStatus = Field(default=ProcessingStatus.PENDING)
    processed_at: Optional[datetime] = Field(None, description="When processing completed")
    posted_reply_id: Optional[str] = Field(None, description="ID of posted reply")
    error_message: Optional[str] = Field(None, description="Error if processing failed")
    retry_count: int = Field(default=0, description="Number of retry attempts")


class VideoInfo(BaseModel):
    """YouTube video information."""

    video_id: str = Field(..., description="Unique video ID")
    title: str = Field(..., description="Video title")
    description: Optional[str] = Field(None, description="Video description")
    published_at: datetime = Field(..., description="When video was published")
    channel_id: str = Field(..., description="Channel ID")
    duration: Optional[str] = Field(None, description="Video duration (ISO 8601)")
    view_count: int = Field(default=0, description="View count")
    like_count: int = Field(default=0, description="Like count")
    comment_count: int = Field(default=0, description="Comment count")
    tags: List[str] = Field(default_factory=list, description="Video tags")
    category_id: Optional[str] = Field(None, description="Category ID")
    transcript_available: bool = Field(default=False, description="Has transcript")


class VideoTranscript(BaseModel):
    """Video transcript data."""

    video_id: str = Field(..., description="Video ID")
    language: str = Field(..., description="Transcript language")
    segments: List["TranscriptSegment"] = Field(..., description="Transcript segments")
    full_text: str = Field(..., description="Complete transcript text")
    is_auto_generated: bool = Field(default=True, description="Auto-generated or manual")


class TranscriptSegment(BaseModel):
    """A segment of video transcript."""

    text: str = Field(..., description="Segment text")
    start: float = Field(..., description="Start time in seconds")
    duration: float = Field(..., description="Duration in seconds")


class CommentBatch(BaseModel):
    """Batch of comments for processing."""

    batch_id: str = Field(..., description="Unique batch ID")
    video_id: Optional[str] = Field(None, description="Video ID if single video batch")
    comments: List[YouTubeComment] = Field(..., description="Comments in batch")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    total_count: int = Field(..., description="Total comments in batch")


class QuotaUsage(BaseModel):
    """YouTube API quota tracking."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    units_used: int = Field(default=0, description="Quota units used")
    units_remaining: int = Field(..., description="Quota units remaining")
    read_operations: int = Field(default=0, description="Read operations count")
    write_operations: int = Field(default=0, description="Write operations count")
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# Update forward references
VideoTranscript.model_rebuild()