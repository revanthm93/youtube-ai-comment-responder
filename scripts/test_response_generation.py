#!/usr/bin/env python3
"""
Test script for end-to-end response generation.

Tests the full pipeline: classification -> generation -> moderation.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.models import YouTubeComment, YouTubeAuthor, ProcessingStatus
from src.agents.classifier import get_classifier
from src.agents.router import get_router


def create_test_comments():
    """Create test comments representing different tiers."""
    return [
        # Tier 1: Simple comment
        YouTubeComment(
            comment_id="test_001",
            video_id="gQPMGDomsR4",
            text="Thanks bro! Great video 🔥",
            author=YouTubeAuthor(
                channel_id="UC_test1",
                channel_url="https://youtube.com/channel/UC_test1",
                display_name="TestUser1",
            ),
            published_at=datetime.now(),
            like_count=5,
        ),
        # Tier 2: Question about content
        YouTubeComment(
            comment_id="test_002",
            video_id="gQPMGDomsR4",
            text="Bro dubai lo ai engineers ki demand vuntunda as a fresher?",
            author=YouTubeAuthor(
                channel_id="UC_test2",
                channel_url="https://youtube.com/channel/UC_test2",
                display_name="TechAspirant",
            ),
            published_at=datetime.now(),
            like_count=10,
        ),
        # Tier 2: Career question
        YouTubeComment(
            comment_id="test_003",
            video_id="gu_r1VEa5to",
            text="What is the salary range for DevOps engineers in UAE? I have 3 years experience.",
            author=YouTubeAuthor(
                channel_id="UC_test3",
                channel_url="https://youtube.com/channel/UC_test3",
                display_name="DevOpsEngineer",
            ),
            published_at=datetime.now(),
            like_count=8,
        ),
        # Tier 3: Complex question
        YouTubeComment(
            comment_id="test_004",
            video_id="gQPMGDomsR4",
            text="Anna, I'm currently working as a manual tester with 4 years experience. I want to switch to AI/ML field. Should I learn Python first or directly jump into ML courses? Also, is it possible to get jobs in Dubai without prior ML experience? Please guide me step by step.",
            author=YouTubeAuthor(
                channel_id="UC_test4",
                channel_url="https://youtube.com/channel/UC_test4",
                display_name="CareerSwitcher",
            ),
            published_at=datetime.now(),
            like_count=15,
        ),
        # Spam comment
        YouTubeComment(
            comment_id="test_005",
            video_id="gQPMGDomsR4",
            text="Check out my channel for free courses! Subscribe to my channel for more!",
            author=YouTubeAuthor(
                channel_id="UC_spam",
                channel_url="https://youtube.com/channel/UC_spam",
                display_name="SpamBot",
            ),
            published_at=datetime.now(),
            like_count=0,
        ),
    ]


def test_classification():
    """Test comment classification."""
    print("\n" + "="*60)
    print("TESTING CLASSIFICATION")
    print("="*60)

    classifier = get_classifier()
    comments = create_test_comments()

    for comment in comments:
        classification = classifier.classify(comment)
        print(f"\n  Comment: \"{comment.text[:50]}...\"")
        print(f"  Type: {classification.comment_type.value}")
        print(f"  Sentiment: {classification.sentiment.value}")
        print(f"  Tier: {classification.response_tier.value}")
        print(f"  Confidence: {classification.confidence:.0%}")
        if classification.topics:
            print(f"  Topics: {classification.topics}")
        if classification.skip_reason:
            print(f"  Skip: {classification.skip_reason}")


def test_full_pipeline():
    """Test the full response generation pipeline."""
    print("\n" + "="*60)
    print("TESTING FULL PIPELINE")
    print("="*60)

    router = get_router()
    comments = create_test_comments()

    for comment in comments:
        print(f"\n{'─'*60}")
        print(f"PROCESSING: {comment.author.display_name}")
        print(f"Comment: \"{comment.text[:60]}{'...' if len(comment.text) > 60 else ''}\"")
        print(f"{'─'*60}")

        result = router.process_comment(comment)

        print(f"\n  Status: {result.status.value}")
        print(f"  Classification:")
        print(f"    Type: {result.classification.comment_type.value}")
        print(f"    Tier: {result.classification.response_tier.value}")

        if result.response:
            print(f"\n  Generated Response:")
            print(f"    \"{result.response.response_text}\"")
            print(f"\n  Metadata:")
            print(f"    Tier used: {result.response.tier_used.value}")
            print(f"    RAG context: {result.response.rag_context_used}")
            print(f"    Model: {result.response.model_used or 'N/A'}")
            print(f"    Time: {result.response.generation_time_ms:.0f}ms")
            if result.response.cost_estimate:
                print(f"    Est. cost: ${result.response.cost_estimate:.6f}")
        elif result.error_message:
            print(f"\n  Error/Skip: {result.error_message}")


def show_stats(results):
    """Show processing statistics."""
    print("\n" + "="*60)
    print("STATISTICS")
    print("="*60)

    total = len(results)
    by_status = {}
    by_tier = {}

    for r in results:
        status = r.status.value
        by_status[status] = by_status.get(status, 0) + 1

        if r.response:
            tier = r.response.tier_used.value
            by_tier[tier] = by_tier.get(tier, 0) + 1

    print(f"\n  Total processed: {total}")
    print(f"\n  By status:")
    for status, count in by_status.items():
        print(f"    {status}: {count}")

    print(f"\n  By tier:")
    for tier, count in by_tier.items():
        print(f"    {tier}: {count}")


def main():
    """Main test function."""
    print("\n" + "="*60)
    print("RESPONSE GENERATION TEST")
    print("="*60)

    # Check Anthropic API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        print("\n  WARNING: ANTHROPIC_API_KEY not configured!")
        print("  Only testing classification (no LLM generation)...")
        test_classification()
        return

    print(f"\n  Anthropic API key: {'*' * 20}{api_key[-4:]}")

    # Test classification first
    test_classification()

    # Test full pipeline
    print("\n" + "="*60)
    print("Ready to test full pipeline with Claude?")
    print("This will make API calls and incur costs.")
    print("="*60)

    response = input("\nProceed? (y/n): ").strip().lower()
    if response != 'y':
        print("Skipping full pipeline test.")
        return

    test_full_pipeline()

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()