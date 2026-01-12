#!/usr/bin/env python3
"""
Test script for YouTube API integration.

This script tests the YouTube Data API v3 connection and fetches comments
from a video to verify the setup is working correctly.

Usage:
    python scripts/test_youtube_api.py [VIDEO_ID]

If VIDEO_ID is not provided, it will try to fetch from your channel's recent videos.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def create_youtube_client():
    """Create a YouTube API client using just the API key (read-only)."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key or api_key == "your_youtube_api_key_here":
        print("ERROR: YOUTUBE_API_KEY not configured in .env file")
        sys.exit(1)

    return build("youtube", "v3", developerKey=api_key)


def get_channel_videos(youtube, channel_id: str, max_results: int = 5):
    """Fetch recent videos from a channel."""
    print(f"\n{'='*60}")
    print(f"Fetching videos from channel: {channel_id}")
    print(f"{'='*60}")

    try:
        request = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=max_results
        )
        response = request.execute()

        videos = []
        for item in response.get("items", []):
            video = {
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
            }
            videos.append(video)
            print(f"\n  Video: {video['title'][:50]}...")
            print(f"  ID: {video['video_id']}")
            print(f"  Published: {video['published_at']}")

        return videos

    except HttpError as e:
        print(f"ERROR fetching videos: {e}")
        return []


def get_video_comments(youtube, video_id: str, max_results: int = 20):
    """Fetch comments from a specific video."""
    print(f"\n{'='*60}")
    print(f"Fetching comments for video: {video_id}")
    print(f"{'='*60}")

    try:
        request = youtube.commentThreads().list(
            part="snippet,replies",
            videoId=video_id,
            maxResults=max_results,
            order="time"
        )
        response = request.execute()

        comments = []
        for item in response.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            comment = {
                "id": item["snippet"]["topLevelComment"]["id"],
                "author": snippet["authorDisplayName"],
                "author_channel_id": snippet.get("authorChannelId", {}).get("value", "unknown"),
                "text": snippet["textDisplay"],
                "published_at": snippet["publishedAt"],
                "like_count": snippet.get("likeCount", 0),
                "reply_count": item["snippet"]["totalReplyCount"],
            }
            comments.append(comment)

            # Check if there are replies from the channel owner
            has_owner_reply = False
            if "replies" in item:
                for reply in item["replies"]["comments"]:
                    reply_author_id = reply["snippet"].get("authorChannelId", {}).get("value", "")
                    # We'll mark this if we had the channel ID
                    pass

            comment["has_owner_reply"] = has_owner_reply

        return comments

    except HttpError as e:
        if "commentsDisabled" in str(e):
            print("  Comments are disabled for this video")
        else:
            print(f"ERROR fetching comments: {e}")
        return []


def display_comments(comments: list, channel_id: str = None):
    """Display comments in a formatted way."""
    if not comments:
        print("  No comments found")
        return

    print(f"\n  Found {len(comments)} comments:\n")

    unanswered = []
    answered = []

    for i, comment in enumerate(comments, 1):
        # Truncate long comments
        text = comment["text"]
        if len(text) > 100:
            text = text[:100] + "..."

        # Remove HTML tags and newlines for display
        text = text.replace("<br>", " ").replace("\n", " ")

        status = ""
        if comment["reply_count"] > 0:
            status = f"[{comment['reply_count']} replies]"
            answered.append(comment)
        else:
            status = "[UNANSWERED]"
            unanswered.append(comment)

        print(f"  {i}. {status}")
        print(f"     Author: {comment['author']}")
        print(f"     Text: {text}")
        print(f"     Likes: {comment['like_count']} | Posted: {comment['published_at'][:10]}")
        print(f"     Comment ID: {comment['id']}")
        print()

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Total comments fetched: {len(comments)}")
    print(f"  With replies: {len(answered)}")
    print(f"  Unanswered: {len(unanswered)}")

    if unanswered:
        print(f"\n  Sample unanswered comments for testing:")
        for c in unanswered[:3]:
            text = c["text"][:80] + "..." if len(c["text"]) > 80 else c["text"]
            text = text.replace("<br>", " ").replace("\n", " ")
            print(f"    - \"{text}\"")


def test_quota_usage(youtube):
    """Display quota usage information."""
    print(f"\n{'='*60}")
    print("QUOTA INFORMATION")
    print(f"{'='*60}")
    print("  YouTube API daily quota: 10,000 units")
    print("  Cost per operation:")
    print("    - List videos: 1 unit")
    print("    - List comments: 1 unit")
    print("    - Post comment: 50 units")
    print("\n  With 10,000 units/day, you can:")
    print("    - Fetch ~10,000 comment batches, OR")
    print("    - Post ~200 replies, OR")
    print("    - Mix of both (recommended: reserve 20% for writes)")


def main():
    """Main test function."""
    print("\n" + "="*60)
    print("YouTube API Integration Test")
    print("="*60)

    # Create client
    youtube = create_youtube_client()
    print("\n  YouTube client created successfully with API key")

    # Get video ID from args or use a test video
    video_id = None
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")

    if len(sys.argv) > 1:
        video_id = sys.argv[1]
        print(f"  Using provided video ID: {video_id}")
    elif channel_id and channel_id != "your_channel_id_here":
        print(f"  Channel ID configured: {channel_id}")
        videos = get_channel_videos(youtube, channel_id, max_results=3)
        if videos:
            video_id = videos[0]["video_id"]
            print(f"\n  Using most recent video: {video_id}")

    if not video_id:
        print("\n  No video ID provided and no channel configured.")
        print("  Please either:")
        print("    1. Set YOUTUBE_CHANNEL_ID in .env, or")
        print("    2. Run with a video ID: python scripts/test_youtube_api.py VIDEO_ID")
        print("\n  Example with a public video:")
        print("    python scripts/test_youtube_api.py dQw4w9WgXcQ")

        # Try a demo with a well-known video
        print("\n  Running demo with sample video...")
        video_id = "dQw4w9WgXcQ"  # Example public video

    # Fetch comments
    comments = get_video_comments(youtube, video_id, max_results=20)

    # Display results
    display_comments(comments, channel_id)

    # Show quota info
    test_quota_usage(youtube)

    print(f"\n{'='*60}")
    print("TEST COMPLETE")
    print(f"{'='*60}")
    print("\n  Next steps:")
    print("    1. Set your YOUTUBE_CHANNEL_ID in .env")
    print("    2. Set up OAuth credentials for posting replies")
    print("    3. Run: python scripts/test_youtube_api.py YOUR_VIDEO_ID")


if __name__ == "__main__":
    main()