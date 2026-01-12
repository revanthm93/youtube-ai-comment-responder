"""
SQLAlchemy database models for persistent storage.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Video(Base):
    """Indexed video record."""

    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(20), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=False)
    channel_id = Column(String(50), nullable=False)
    transcript_indexed = Column(Boolean, default=False)
    transcript_language = Column(String(10), nullable=True)
    chunks_count = Column(Integer, default=0)
    last_indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    comments = relationship("Comment", back_populates="video", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_videos_channel_published", "channel_id", "published_at"),
    )


class Comment(Base):
    """Processed comment record."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comment_id = Column(String(50), unique=True, nullable=False, index=True)
    video_id = Column(String(20), ForeignKey("videos.video_id"), nullable=False, index=True)
    parent_comment_id = Column(String(50), nullable=True, index=True)
    author_channel_id = Column(String(50), nullable=False)
    author_name = Column(String(200), nullable=False)
    text = Column(Text, nullable=False)
    published_at = Column(DateTime, nullable=False)
    like_count = Column(Integer, default=0)

    # Classification
    comment_type = Column(String(20), nullable=True)
    sentiment = Column(String(20), nullable=True)
    response_tier = Column(String(30), nullable=True)
    classification_confidence = Column(Float, nullable=True)
    detected_language = Column(String(10), nullable=True)

    # Processing status
    status = Column(String(20), default="pending", nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    video = relationship("Video", back_populates="comments")
    response = relationship("Response", back_populates="comment", uselist=False)

    __table_args__ = (
        Index("ix_comments_status_created", "status", "created_at"),
        Index("ix_comments_video_status", "video_id", "status"),
    )


class Response(Base):
    """Generated response record."""

    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comment_id = Column(String(50), ForeignKey("comments.comment_id"), unique=True, nullable=False)
    response_text = Column(Text, nullable=False)
    tier_used = Column(String(30), nullable=False)
    model_used = Column(String(50), nullable=True)
    rag_context_used = Column(Boolean, default=False)
    generation_time_ms = Column(Float, nullable=True)
    token_count = Column(Integer, nullable=True)
    cost_estimate = Column(Float, nullable=True)

    # Posting status
    posted = Column(Boolean, default=False)
    posted_at = Column(DateTime, nullable=True)
    posted_reply_id = Column(String(50), nullable=True)

    # Moderation
    moderation_passed = Column(Boolean, default=True)
    moderation_issues = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    comment = relationship("Comment", back_populates="response")


class QuotaLog(Base):
    """Daily API quota tracking."""

    __tablename__ = "quota_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD
    units_used = Column(Integer, default=0)
    read_operations = Column(Integer, default=0)
    write_operations = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProcessingBatch(Base):
    """Batch processing record."""

    __tablename__ = "processing_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(50), unique=True, nullable=False, index=True)
    video_id = Column(String(20), nullable=True)
    total_comments = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    status = Column(String(20), default="pending")
    celery_task_id = Column(String(50), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemMetrics(Base):
    """System metrics for monitoring."""

    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    tags = Column(Text, nullable=True)  # JSON string
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_metrics_name_time", "metric_name", "recorded_at"),
    )