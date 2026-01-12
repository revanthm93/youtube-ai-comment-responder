"""
Pytest configuration and shared fixtures.
"""

import os
from datetime import datetime
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set test environment before importing app modules
os.environ["APP_ENV"] = "testing"
os.environ["DEBUG"] = "true"
os.environ["DRY_RUN"] = "true"
os.environ["YOUTUBE_API_KEY"] = "test_api_key"
os.environ["YOUTUBE_CLIENT_ID"] = "test_client_id"
os.environ["YOUTUBE_CLIENT_SECRET"] = "test_client_secret"
os.environ["YOUTUBE_REFRESH_TOKEN"] = "test_refresh_token"
os.environ["YOUTUBE_CHANNEL_ID"] = "test_channel_id"
os.environ["ANTHROPIC_API_KEY"] = "test_anthropic_key"


@pytest.fixture(scope="session")
def mock_env():
    """Set up test environment variables."""
    env_vars = {
        "APP_ENV": "testing",
        "DEBUG": "true",
        "DRY_RUN": "true",
        "YOUTUBE_API_KEY": "test_api_key",
        "YOUTUBE_CLIENT_ID": "test_client_id",
        "YOUTUBE_CLIENT_SECRET": "test_client_secret",
        "YOUTUBE_REFRESH_TOKEN": "test_refresh_token",
        "YOUTUBE_CHANNEL_ID": "test_channel_id",
        "ANTHROPIC_API_KEY": "test_anthropic_key",
        "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
    }
    with patch.dict(os.environ, env_vars):
        yield


@pytest.fixture
def sample_youtube_comment():
    """Create a sample YouTube comment for testing."""
    from src.models import YouTubeComment, YouTubeAuthor

    return YouTubeComment(
        comment_id="test_comment_123",
        video_id="test_video_456",
        text="Great video! Can you share more about UAE visa process?",
        author=YouTubeAuthor(
            channel_id="UC_test_author",
            channel_url="https://youtube.com/channel/UC_test_author",
            display_name="Test Viewer",
            profile_image_url="https://example.com/avatar.jpg",
        ),
        published_at=datetime(2024, 1, 15, 10, 30, 0),
        like_count=5,
        reply_count=0,
    )


@pytest.fixture
def sample_comments_batch():
    """Create a batch of sample comments for testing."""
    from src.models import YouTubeComment, YouTubeAuthor

    comments = [
        YouTubeComment(
            comment_id=f"comment_{i}",
            video_id="video_123",
            text=text,
            author=YouTubeAuthor(
                channel_id=f"UC_author_{i}",
                channel_url=f"https://youtube.com/channel/UC_author_{i}",
                display_name=f"User {i}",
            ),
            published_at=datetime(2024, 1, 15, 10, i, 0),
            like_count=i,
        )
        for i, text in enumerate([
            "Thanks for the video!",
            "What is the salary range for IT jobs in Dubai?",
            "Can you make a video about cost of living?",
            "Nice explanation bro",
            "I'm planning to move to UAE next year. What documents do I need?",
        ])
    ]
    return comments


@pytest.fixture
def mock_youtube_client():
    """Create a mocked YouTube client."""
    from src.youtube.client import YouTubeClient

    with patch.object(YouTubeClient, "initialize") as mock_init:
        mock_init.return_value = None
        client = YouTubeClient()
        client._initialized = True
        client._service = MagicMock()
        yield client


@pytest.fixture
def mock_anthropic_client():
    """Create a mocked Anthropic client."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="Test response from Claude")],
        usage=MagicMock(input_tokens=100, output_tokens=50),
    )
    return mock_client


@pytest.fixture
def test_client(mock_env) -> Generator[TestClient, None, None]:
    """Create a FastAPI test client."""
    from src.api.app import app

    with TestClient(app) as client:
        yield client