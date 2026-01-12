"""
YouTube Data API v3 client wrapper.

Handles authentication, rate limiting, quota tracking, and provides
a clean interface for comment operations.
"""

import asyncio
from datetime import datetime, date
from typing import AsyncGenerator, List, Optional, Tuple

import structlog
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import get_youtube_settings, get_response_settings
from src.models import (
    YouTubeAuthor,
    YouTubeComment,
    VideoInfo,
    QuotaUsage,
)

logger = structlog.get_logger(__name__)


# YouTube API quota costs
QUOTA_COSTS = {
    "list_comments": 1,
    "list_comment_threads": 1,
    "insert_comment": 50,
    "list_videos": 1,
    "list_channels": 1,
    "list_subscriptions": 1,
}


class QuotaExceededError(Exception):
    """Raised when YouTube API quota is exceeded."""

    pass


class YouTubeAPIError(Exception):
    """General YouTube API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class YouTubeClient:
    """
    YouTube Data API v3 client with quota management and retry logic.

    Usage:
        async with YouTubeClient() as client:
            comments = await client.get_unanswered_comments(video_id)
    """

    def __init__(self):
        self.settings = get_youtube_settings()
        self.response_settings = get_response_settings()
        self._service = None
        self._quota_usage: Optional[QuotaUsage] = None
        self._initialized = False

    async def __aenter__(self) -> "YouTubeClient":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def initialize(self) -> None:
        """Initialize the YouTube API service."""
        if self._initialized:
            return

        try:
            # Create credentials from refresh token
            credentials = Credentials(
                token=None,
                refresh_token=self.settings.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.settings.client_id,
                client_secret=self.settings.client_secret,
            )

            # Build the service (runs in thread pool since it's sync)
            loop = asyncio.get_event_loop()
            self._service = await loop.run_in_executor(
                None,
                lambda: build("youtube", "v3", credentials=credentials),
            )

            # Initialize quota tracking for today
            self._quota_usage = QuotaUsage(
                date=date.today().isoformat(),
                units_used=0,
                units_remaining=self.settings.daily_quota_limit,
            )

            self._initialized = True
            logger.info("youtube_client_initialized", channel_id=self.settings.channel_id)

        except Exception as e:
            logger.error("youtube_client_init_failed", error=str(e))
            raise YouTubeAPIError(f"Failed to initialize YouTube client: {e}")

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        if self._service:
            self._service.close()
            self._service = None
        self._initialized = False
        logger.info("youtube_client_closed")

    def _check_quota(self, operation: str) -> None:
        """Check if we have enough quota for an operation."""
        cost = QUOTA_COSTS.get(operation, 1)
        if self._quota_usage.units_remaining < cost + self.settings.quota_reserve:
            raise QuotaExceededError(
                f"Insufficient quota for {operation}. "
                f"Remaining: {self._quota_usage.units_remaining}, "
                f"Required: {cost}"
            )

    def _record_quota_usage(self, operation: str) -> None:
        """Record quota usage for an operation."""
        cost = QUOTA_COSTS.get(operation, 1)
        self._quota_usage.units_used += cost
        self._quota_usage.units_remaining -= cost
        self._quota_usage.last_updated = datetime.utcnow()

        if operation.startswith("list"):
            self._quota_usage.read_operations += 1
        elif operation.startswith("insert"):
            self._quota_usage.write_operations += 1

        logger.debug(
            "quota_used",
            operation=operation,
            cost=cost,
            total_used=self._quota_usage.units_used,
            remaining=self._quota_usage.units_remaining,
        )

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _execute_request(self, request, operation: str):
        """Execute a YouTube API request with retry logic."""
        self._check_quota(operation)

        try:
            # Run synchronous API call in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, request.execute)
            self._record_quota_usage(operation)

            # Respect rate limits
            await asyncio.sleep(self.settings.api_delay)
            return result

        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                logger.error("youtube_quota_exceeded", error=str(e))
                raise QuotaExceededError("YouTube API quota exceeded")
            logger.error(
                "youtube_api_error",
                status=e.resp.status,
                error=str(e),
                operation=operation,
            )
            raise

    async def get_channel_videos(
        self,
        max_results: int = 50,
        published_after: Optional[datetime] = None,
    ) -> List[VideoInfo]:
        """
        Get videos from the authenticated channel.

        Args:
            max_results: Maximum number of videos to fetch
            published_after: Only get videos published after this date

        Returns:
            List of VideoInfo objects
        """
        if not self._initialized:
            await self.initialize()

        videos = []
        page_token = None

        while len(videos) < max_results:
            request_params = {
                "channelId": self.settings.channel_id,
                "part": "snippet,statistics,contentDetails",
                "type": "video",
                "order": "date",
                "maxResults": min(50, max_results - len(videos)),
            }

            if page_token:
                request_params["pageToken"] = page_token
            if published_after:
                request_params["publishedAfter"] = published_after.isoformat() + "Z"

            request = self._service.search().list(**request_params)
            response = await self._execute_request(request, "list_videos")

            for item in response.get("items", []):
                video_id = item["id"]["videoId"]
                snippet = item["snippet"]

                # Get detailed video info
                video_details = await self._get_video_details(video_id)
                if video_details:
                    videos.append(video_details)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.info("fetched_channel_videos", count=len(videos))
        return videos

    async def _get_video_details(self, video_id: str) -> Optional[VideoInfo]:
        """Get detailed information for a single video."""
        request = self._service.videos().list(
            part="snippet,statistics,contentDetails",
            id=video_id,
        )
        response = await self._execute_request(request, "list_videos")

        items = response.get("items", [])
        if not items:
            return None

        item = items[0]
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        return VideoInfo(
            video_id=video_id,
            title=snippet["title"],
            description=snippet.get("description"),
            published_at=datetime.fromisoformat(
                snippet["publishedAt"].replace("Z", "+00:00")
            ),
            channel_id=snippet["channelId"],
            duration=content.get("duration"),
            view_count=int(stats.get("viewCount", 0)),
            like_count=int(stats.get("likeCount", 0)),
            comment_count=int(stats.get("commentCount", 0)),
            tags=snippet.get("tags", []),
            category_id=snippet.get("categoryId"),
        )

    async def get_video_comments(
        self,
        video_id: str,
        max_results: int = 100,
        include_replies: bool = False,
    ) -> List[YouTubeComment]:
        """
        Get comments for a specific video.

        Args:
            video_id: YouTube video ID
            max_results: Maximum comments to fetch
            include_replies: Whether to include reply threads

        Returns:
            List of YouTubeComment objects
        """
        if not self._initialized:
            await self.initialize()

        comments = []
        page_token = None

        while len(comments) < max_results:
            request = self._service.commentThreads().list(
                part="snippet,replies" if include_replies else "snippet",
                videoId=video_id,
                maxResults=min(100, max_results - len(comments)),
                order="time",
                pageToken=page_token,
            )

            response = await self._execute_request(request, "list_comment_threads")

            for thread in response.get("items", []):
                # Top-level comment
                top_comment = self._parse_comment(
                    thread["snippet"]["topLevelComment"],
                    video_id,
                )
                top_comment.reply_count = thread["snippet"]["totalReplyCount"]
                comments.append(top_comment)

                # Include replies if requested
                if include_replies and "replies" in thread:
                    for reply in thread["replies"]["comments"]:
                        reply_comment = self._parse_comment(reply, video_id)
                        reply_comment.parent_id = top_comment.comment_id
                        reply_comment.is_reply = True
                        comments.append(reply_comment)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.info(
            "fetched_video_comments",
            video_id=video_id,
            count=len(comments),
        )
        return comments

    async def get_unanswered_comments(
        self,
        video_id: Optional[str] = None,
        max_results: int = 50,
    ) -> List[YouTubeComment]:
        """
        Get comments that haven't been replied to by the channel owner.

        Args:
            video_id: Specific video ID (if None, gets from recent videos)
            max_results: Maximum comments to return

        Returns:
            List of unanswered YouTubeComment objects
        """
        if not self._initialized:
            await self.initialize()

        if video_id:
            video_ids = [video_id]
        else:
            # Get recent videos
            videos = await self.get_channel_videos(max_results=10)
            video_ids = [v.video_id for v in videos]

        unanswered = []

        for vid in video_ids:
            if len(unanswered) >= max_results:
                break

            comments = await self.get_video_comments(
                vid,
                max_results=100,
                include_replies=True,
            )

            # Filter to unanswered: top-level comments without owner reply
            owner_replied_to = set()
            for comment in comments:
                if comment.is_reply and comment.author.channel_id == self.settings.channel_id:
                    if comment.parent_id:
                        owner_replied_to.add(comment.parent_id)

            for comment in comments:
                if (
                    not comment.is_reply
                    and comment.comment_id not in owner_replied_to
                    and comment.author.channel_id != self.settings.channel_id
                ):
                    unanswered.append(comment)
                    if len(unanswered) >= max_results:
                        break

        logger.info(
            "fetched_unanswered_comments",
            video_id=video_id,
            count=len(unanswered),
        )
        return unanswered

    async def get_all_unanswered_comments(
        self,
        max_results: int = 100,
    ) -> AsyncGenerator[YouTubeComment, None]:
        """
        Async generator that yields unanswered comments across channel videos.

        Args:
            max_results: Maximum total comments to yield

        Yields:
            YouTubeComment objects
        """
        if not self._initialized:
            await self.initialize()

        videos = await self.get_channel_videos(max_results=20)
        count = 0

        for video in videos:
            if count >= max_results:
                break

            comments = await self.get_unanswered_comments(
                video_id=video.video_id,
                max_results=min(50, max_results - count),
            )

            for comment in comments:
                yield comment
                count += 1
                if count >= max_results:
                    break

    async def post_reply(
        self,
        parent_comment_id: str,
        reply_text: str,
    ) -> str:
        """
        Post a reply to a comment.

        Args:
            parent_comment_id: ID of the comment to reply to
            reply_text: Text of the reply

        Returns:
            ID of the posted reply
        """
        if not self._initialized:
            await self.initialize()

        request = self._service.comments().insert(
            part="snippet",
            body={
                "snippet": {
                    "parentId": parent_comment_id,
                    "textOriginal": reply_text,
                }
            },
        )

        response = await self._execute_request(request, "insert_comment")
        reply_id = response["id"]

        logger.info(
            "posted_reply",
            parent_comment_id=parent_comment_id,
            reply_id=reply_id,
            reply_length=len(reply_text),
        )

        return reply_id

    def _parse_comment(self, comment_data: dict, video_id: str) -> YouTubeComment:
        """Parse YouTube API comment data into YouTubeComment model."""
        snippet = comment_data["snippet"]
        author = snippet.get("authorChannelId", {})

        return YouTubeComment(
            comment_id=comment_data["id"],
            video_id=video_id,
            text=snippet["textDisplay"],
            author=YouTubeAuthor(
                channel_id=author.get("value", "unknown"),
                channel_url=snippet.get("authorChannelUrl", ""),
                display_name=snippet["authorDisplayName"],
                profile_image_url=snippet.get("authorProfileImageUrl"),
            ),
            published_at=datetime.fromisoformat(
                snippet["publishedAt"].replace("Z", "+00:00")
            ),
            updated_at=(
                datetime.fromisoformat(snippet["updatedAt"].replace("Z", "+00:00"))
                if "updatedAt" in snippet
                else None
            ),
            like_count=snippet.get("likeCount", 0),
        )

    def get_quota_status(self) -> QuotaUsage:
        """Get current quota usage status."""
        return self._quota_usage

    def can_write(self) -> bool:
        """Check if we have enough quota for write operations."""
        if not self._quota_usage:
            return True
        write_cost = QUOTA_COSTS["insert_comment"]
        return self._quota_usage.units_remaining > write_cost + self.settings.quota_reserve

    def can_read(self) -> bool:
        """Check if we have enough quota for read operations."""
        if not self._quota_usage:
            return True
        return self._quota_usage.units_remaining > self.settings.quota_reserve