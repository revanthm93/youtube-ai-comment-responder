"""
Unit tests for YouTube API client.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import YouTubeComment, YouTubeAuthor, QuotaUsage
from src.youtube.client import YouTubeClient, QuotaExceededError, QUOTA_COSTS


class TestQuotaCosts:
    """Test quota cost definitions."""

    def test_read_operations_cost_one_unit(self):
        """Read operations should cost 1 unit."""
        read_ops = ["list_comments", "list_comment_threads", "list_videos", "list_channels"]
        for op in read_ops:
            assert QUOTA_COSTS[op] == 1, f"{op} should cost 1 unit"

    def test_write_operations_cost_fifty_units(self):
        """Write operations should cost 50 units."""
        assert QUOTA_COSTS["insert_comment"] == 50


class TestYouTubeClientQuota:
    """Test quota management functionality."""

    @pytest.fixture
    def client(self):
        """Create a client instance with mocked settings."""
        with patch("src.youtube.client.get_youtube_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                api_key="test_key",
                client_id="test_client_id",
                client_secret="test_secret",
                refresh_token="test_refresh",
                channel_id="test_channel",
                daily_quota_limit=10000,
                quota_reserve=1000,
                api_delay=0.0,
            )
            with patch("src.youtube.client.get_response_settings") as mock_response:
                mock_response.return_value = MagicMock()
                client = YouTubeClient()
                # Manually set up quota for testing
                client._quota_usage = QuotaUsage(
                    date="2024-01-01",
                    units_used=0,
                    units_remaining=10000,
                )
                return client

    def test_can_read_with_sufficient_quota(self, client):
        """Should return True when quota is sufficient for reads."""
        client._quota_usage.units_remaining = 2000
        assert client.can_read() is True

    def test_can_read_with_insufficient_quota(self, client):
        """Should return False when quota is below reserve."""
        client._quota_usage.units_remaining = 500  # Below 1000 reserve
        assert client.can_read() is False

    def test_can_write_with_sufficient_quota(self, client):
        """Should return True when quota is sufficient for writes."""
        client._quota_usage.units_remaining = 2000
        assert client.can_write() is True

    def test_can_write_with_insufficient_quota(self, client):
        """Should return False when quota is below write cost + reserve."""
        client._quota_usage.units_remaining = 1040  # 50 (write) + 1000 (reserve) = 1050 needed
        assert client.can_write() is False

    def test_check_quota_raises_when_exceeded(self, client):
        """Should raise QuotaExceededError when quota is insufficient."""
        client._quota_usage.units_remaining = 500
        with pytest.raises(QuotaExceededError):
            client._check_quota("insert_comment")

    def test_record_quota_usage_decrements_remaining(self, client):
        """Recording usage should decrement remaining units."""
        initial_remaining = client._quota_usage.units_remaining
        client._record_quota_usage("list_comments")
        assert client._quota_usage.units_remaining == initial_remaining - 1
        assert client._quota_usage.units_used == 1
        assert client._quota_usage.read_operations == 1

    def test_record_quota_usage_tracks_write_operations(self, client):
        """Should track write operations separately."""
        client._record_quota_usage("insert_comment")
        assert client._quota_usage.write_operations == 1
        assert client._quota_usage.units_used == 50


class TestCommentParsing:
    """Test comment data parsing."""

    @pytest.fixture
    def client(self):
        """Create a client instance."""
        with patch("src.youtube.client.get_youtube_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            with patch("src.youtube.client.get_response_settings"):
                return YouTubeClient()

    def test_parse_comment_extracts_all_fields(self, client):
        """Should correctly parse YouTube API comment response."""
        comment_data = {
            "id": "comment123",
            "snippet": {
                "textDisplay": "Great video! Thanks for sharing.",
                "authorDisplayName": "Test User",
                "authorChannelUrl": "https://youtube.com/channel/UC123",
                "authorChannelId": {"value": "UC123"},
                "authorProfileImageUrl": "https://example.com/avatar.jpg",
                "publishedAt": "2024-01-15T10:30:00Z",
                "likeCount": 5,
            },
        }

        comment = client._parse_comment(comment_data, "video123")

        assert comment.comment_id == "comment123"
        assert comment.video_id == "video123"
        assert comment.text == "Great video! Thanks for sharing."
        assert comment.author.display_name == "Test User"
        assert comment.author.channel_id == "UC123"
        assert comment.like_count == 5

    def test_parse_comment_handles_missing_optional_fields(self, client):
        """Should handle comments with missing optional fields."""
        comment_data = {
            "id": "comment456",
            "snippet": {
                "textDisplay": "Nice!",
                "authorDisplayName": "User",
                "authorChannelUrl": "",
                "authorChannelId": {},
                "publishedAt": "2024-01-15T10:30:00Z",
            },
        }

        comment = client._parse_comment(comment_data, "video456")

        assert comment.comment_id == "comment456"
        assert comment.author.channel_id == "unknown"
        assert comment.like_count == 0


class TestQuotaUsageModel:
    """Test QuotaUsage model."""

    def test_quota_usage_creation(self):
        """Should create QuotaUsage with correct defaults."""
        quota = QuotaUsage(
            date="2024-01-15",
            units_used=100,
            units_remaining=9900,
        )

        assert quota.date == "2024-01-15"
        assert quota.units_used == 100
        assert quota.units_remaining == 9900
        assert quota.read_operations == 0
        assert quota.write_operations == 0