#!/usr/bin/env python3
"""
Reply to real YouTube comments.

Fetches unanswered comments, generates AI responses, and displays them for manual posting.

IMPORTANT: YouTube API Limitation
---------------------------------
As of 2020, Google requires apps to pass a compliance audit before they can
post comments via the YouTube Data API. This is a spam prevention measure.

To enable auto-posting:
1. Go to https://console.cloud.google.com/apis/credentials/consent
2. Submit your app for OAuth verification
3. Fill out YouTube API audit form: https://support.google.com/youtube/contact/yt_api_form
4. Wait 4-6 weeks for approval

Until then, this script generates responses for MANUAL copy-paste.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Suppress tokenizers warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.models import YouTubeComment, YouTubeAuthor, ProcessingStatus
from src.agents.router import get_router


def get_youtube_client():
    """Create authenticated YouTube client."""
    credentials = Credentials(
        token=None,
        refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YOUTUBE_CLIENT_ID"),
        client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
    )
    return build("youtube", "v3", credentials=credentials)


def fetch_unanswered_comments(youtube, max_results=10):
    """Fetch unanswered comments from recent videos."""
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")

    # Get recent videos
    videos_response = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        type="video",
        order="date",
        maxResults=5
    ).execute()

    all_comments = []

    for video in videos_response.get("items", []):
        video_id = video["id"]["videoId"]
        video_title = video["snippet"]["title"]

        try:
            # Fetch comments for this video
            comments_response = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=50,
                order="time"
            ).execute()

            # Find which comments have owner replies
            owner_replied = set()
            for thread in comments_response.get("items", []):
                if "replies" in thread:
                    for reply in thread["replies"]["comments"]:
                        reply_author = reply["snippet"].get("authorChannelId", {}).get("value", "")
                        if reply_author == channel_id:
                            owner_replied.add(thread["snippet"]["topLevelComment"]["id"])

            # Collect unanswered comments
            for thread in comments_response.get("items", []):
                comment_data = thread["snippet"]["topLevelComment"]
                comment_id = comment_data["id"]

                # Skip if already replied or is own comment
                author_channel = comment_data["snippet"].get("authorChannelId", {}).get("value", "")
                if comment_id in owner_replied or author_channel == channel_id:
                    continue

                snippet = comment_data["snippet"]
                comment = {
                    "comment_id": comment_id,
                    "video_id": video_id,
                    "video_title": video_title,
                    "text": snippet["textDisplay"],
                    "author_name": snippet["authorDisplayName"],
                    "author_channel_id": author_channel,
                    "published_at": snippet["publishedAt"],
                    "like_count": snippet.get("likeCount", 0),
                }
                all_comments.append(comment)

                if len(all_comments) >= max_results:
                    break

        except Exception as e:
            print(f"  Error fetching comments for {video_id}: {e}")
            continue

        if len(all_comments) >= max_results:
            break

    return all_comments


def post_reply(youtube, comment_id: str, reply_text: str) -> str:
    """
    Post a reply to a comment.

    NOTE: This function requires YouTube API compliance audit approval.
    Will return 403 error until the app passes Google's review process.
    See module docstring for details on how to get approved.
    """
    response = youtube.comments().insert(
        part="snippet",
        body={
            "snippet": {
                "parentId": comment_id,
                "textOriginal": reply_text,
            }
        }
    ).execute()
    return response["id"]


def main():
    print("\n" + "="*60)
    print("YOUTUBE COMMENT REPLIER")
    print("="*60)

    # Initialize
    youtube = get_youtube_client()
    router = get_router()

    # Fetch unanswered comments
    print("\nFetching unanswered comments...")
    comments = fetch_unanswered_comments(youtube, max_results=10)

    if not comments:
        print("No unanswered comments found!")
        return

    print(f"\nFound {len(comments)} unanswered comments:\n")

    # Process each comment
    results = []
    for i, comment_data in enumerate(comments, 1):
        print(f"{'─'*60}")
        print(f"[{i}/{len(comments)}] {comment_data['author_name']}")
        print(f"Video: {comment_data['video_title'][:40]}...")
        print(f"Comment: \"{comment_data['text'][:80]}{'...' if len(comment_data['text']) > 80 else ''}\"")

        # Convert to YouTubeComment model
        comment = YouTubeComment(
            comment_id=comment_data["comment_id"],
            video_id=comment_data["video_id"],
            text=comment_data["text"],
            author=YouTubeAuthor(
                channel_id=comment_data["author_channel_id"],
                channel_url=f"https://youtube.com/channel/{comment_data['author_channel_id']}",
                display_name=comment_data["author_name"],
            ),
            published_at=datetime.fromisoformat(comment_data["published_at"].replace("Z", "+00:00")),
            like_count=comment_data["like_count"],
        )

        # Process through pipeline
        result = router.process_comment(comment, video_title=comment_data["video_title"])

        if result.status == ProcessingStatus.RESPONDED and result.response:
            print(f"\n  → Generated Response ({result.response.tier_used.value}):")
            print(f"    \"{result.response.response_text}\"")
            results.append({
                "comment_data": comment_data,
                "result": result,
            })
        elif result.status == ProcessingStatus.SKIPPED:
            print(f"\n  → Skipped: {result.error_message}")
        else:
            print(f"\n  → Failed: {result.error_message}")

        print()

    if not results:
        print("No responses generated.")
        return

    # Display responses for manual copy-paste
    print("\n" + "="*60)
    print("GENERATED RESPONSES - COPY & PASTE MANUALLY")
    print("="*60)
    print("\nNOTE: Auto-posting requires YouTube API compliance audit.")
    print("Until approved, please copy-paste these responses manually.\n")

    for i, r in enumerate(results, 1):
        comment_data = r["comment_data"]
        response_text = r["result"].response.response_text
        video_url = f"https://www.youtube.com/watch?v={comment_data['video_id']}&lc={comment_data['comment_id']}"

        print("─" * 60)
        print(f"[{i}] Reply to: @{comment_data['author_name']}")
        print(f"    Video: {comment_data['video_title'][:50]}...")
        print(f"    Comment: \"{comment_data['text'][:60]}{'...' if len(comment_data['text']) > 60 else ''}\"")
        print(f"\n    📋 RESPONSE TO COPY:")
        print(f"    ┌{'─'*54}┐")
        # Wrap response text for display
        words = response_text.split()
        lines = []
        current_line = []
        for word in words:
            if len(' '.join(current_line + [word])) <= 52:
                current_line.append(word)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        for line in lines:
            print(f"    │ {line:<52} │")
        print(f"    └{'─'*54}┘")
        print(f"\n    🔗 Link: {video_url}")
        print()

    print("="*60)
    print(f"TOTAL: {len(results)} responses generated")
    print("="*60)
    print("\nTip: Click each link, find the comment, and paste the response.")
    print("     The link should scroll directly to the comment.\n")


if __name__ == "__main__":
    main()