"""
Configuration management using Pydantic Settings.

Loads configuration from environment variables with validation and type coercion.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class YouTubeSettings(BaseSettings):
    """YouTube API configuration."""

    model_config = SettingsConfigDict(env_prefix="YOUTUBE_")

    api_key: str = Field(..., description="YouTube Data API v3 key")
    client_id: str = Field(..., description="OAuth 2.0 client ID")
    client_secret: str = Field(..., description="OAuth 2.0 client secret")
    refresh_token: str = Field(..., description="OAuth 2.0 refresh token")
    channel_id: str = Field(..., description="Your YouTube channel ID")
    daily_quota_limit: int = Field(default=10000, description="Daily API quota limit")
    quota_reserve: int = Field(default=1000, description="Reserved quota for critical ops")
    api_delay: float = Field(default=1.0, description="Delay between API calls (seconds)")


class AnthropicSettings(BaseSettings):
    """Anthropic Claude API configuration."""

    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_")

    api_key: str = Field(..., description="Anthropic API key")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model to use")
    max_tokens: int = Field(default=1024, description="Max tokens per response")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0, description="Response temperature")


class RedisSettings(BaseSettings):
    """Redis configuration for Celery."""

    url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    broker_url: str = Field(
        default="redis://localhost:6379/0",
        alias="CELERY_BROKER_URL"
    )
    result_backend: str = Field(
        default="redis://localhost:6379/1",
        alias="CELERY_RESULT_BACKEND"
    )


class ChromaSettings(BaseSettings):
    """ChromaDB vector store configuration."""

    model_config = SettingsConfigDict(env_prefix="CHROMA_")

    persist_directory: str = Field(default="./data/chroma", description="ChromaDB storage path")
    collection_name: str = Field(default="video_transcripts", description="Collection name")


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    url: str = Field(
        default="sqlite+aiosqlite:///./data/app.db",
        alias="DATABASE_URL",
        description="Database connection URL"
    )


class APISettings(BaseSettings):
    """FastAPI application settings."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = Field(default="0.0.0.0", description="API host")
    port: int = Field(default=8000, description="API port")
    prefix: str = Field(default="/api/v1", description="API prefix")


class ChannelSettings(BaseSettings):
    """Channel context for personalized responses."""

    model_config = SettingsConfigDict(env_prefix="CHANNEL_")

    name: str = Field(default="Revanth", description="Channel name")
    language: str = Field(default="Telugu,English", description="Languages used")
    topics: str = Field(
        default="UAE relocation,IT careers,career guidance,global migration",
        description="Channel topics"
    )
    tone: str = Field(
        default="authentic,conversational,helpful",
        description="Response tone"
    )

    @property
    def languages(self) -> List[str]:
        """Parse language string into list."""
        return [lang.strip() for lang in self.language.split(",")]

    @property
    def topic_list(self) -> List[str]:
        """Parse topics string into list."""
        return [topic.strip() for topic in self.topics.split(",")]

    @property
    def tone_descriptors(self) -> List[str]:
        """Parse tone string into list."""
        return [t.strip() for t in self.tone.split(",")]


class ResponseSettings(BaseSettings):
    """Response generation settings."""

    tier1_max_tokens: int = Field(
        default=20,
        alias="TIER1_MAX_TOKENS",
        description="Max tokens for Tier 1 (simple) comments"
    )
    tier2_similarity_threshold: float = Field(
        default=0.75,
        alias="TIER2_RAG_SIMILARITY_THRESHOLD",
        description="Min similarity for RAG retrieval"
    )
    enable_moderation: bool = Field(
        default=True,
        alias="ENABLE_CONTENT_MODERATION",
        description="Enable content moderation"
    )
    max_response_length: int = Field(
        default=500,
        alias="MAX_RESPONSE_LENGTH",
        description="Max response character length"
    )
    max_comments_per_batch: int = Field(
        default=50,
        alias="MAX_COMMENTS_PER_BATCH",
        description="Max comments to process per batch"
    )


class CelerySettings(BaseSettings):
    """Celery worker settings."""

    model_config = SettingsConfigDict(env_prefix="CELERY_")

    task_serializer: str = Field(default="json")
    result_serializer: str = Field(default="json")
    accept_content: str = Field(default="json")
    timezone: str = Field(default="UTC")
    task_track_started: bool = Field(default=True)
    task_time_limit: int = Field(default=300)


class Settings(BaseSettings):
    """Main application settings aggregating all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application
    app_name: str = Field(default="YouTube AI Comment Responder", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Security
    secret_key: str = Field(default="dev-secret-key-change-in-production", alias="SECRET_KEY")
    api_key: Optional[str] = Field(default=None, alias="API_KEY")

    # CORS
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        alias="CORS_ORIGINS"
    )

    # Feature flags
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    enable_debug_endpoints: bool = Field(default=True, alias="ENABLE_DEBUG_ENDPOINTS")
    enable_metrics: bool = Field(default=True, alias="ENABLE_METRICS")
    metrics_port: int = Field(default=9090, alias="METRICS_PORT")

    # Embedding model
    embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")

    # Optional integrations
    sentry_dsn: Optional[str] = Field(default=None, alias="SENTRY_DSN")

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.app_env.lower() == "development"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


@lru_cache
def get_youtube_settings() -> YouTubeSettings:
    """Get cached YouTube settings."""
    return YouTubeSettings()


@lru_cache
def get_anthropic_settings() -> AnthropicSettings:
    """Get cached Anthropic settings."""
    return AnthropicSettings()


@lru_cache
def get_redis_settings() -> RedisSettings:
    """Get cached Redis settings."""
    return RedisSettings()


@lru_cache
def get_chroma_settings() -> ChromaSettings:
    """Get cached ChromaDB settings."""
    return ChromaSettings()


@lru_cache
def get_database_settings() -> DatabaseSettings:
    """Get cached database settings."""
    return DatabaseSettings()


@lru_cache
def get_api_settings() -> APISettings:
    """Get cached API settings."""
    return APISettings()


@lru_cache
def get_channel_settings() -> ChannelSettings:
    """Get cached channel settings."""
    return ChannelSettings()


@lru_cache
def get_response_settings() -> ResponseSettings:
    """Get cached response settings."""
    return ResponseSettings()


@lru_cache
def get_celery_settings() -> CelerySettings:
    """Get cached Celery settings."""
    return CelerySettings()