#!/usr/bin/env python3
"""
Test script for RAG pipeline.

Tests transcript fetching, indexing, and retrieval.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.rag.indexer import TranscriptIndexer
from src.rag.retriever import ContextRetriever
from src.rag.vector_store import get_vector_store


async def test_index_video(video_id: str, video_title: str = None):
    """Test indexing a single video."""
    print(f"\n{'='*60}")
    print(f"INDEXING VIDEO: {video_id}")
    print(f"{'='*60}")

    indexer = TranscriptIndexer()
    result = await indexer.index_video(
        video_id=video_id,
        video_title=video_title,
        force_reindex=True,
    )

    print(f"\n  Success: {result.success}")
    print(f"  Chunks indexed: {result.chunks_indexed}")
    print(f"  Language: {result.language}")
    if result.error:
        print(f"  Error: {result.error}")

    return result


def test_retrieval(query: str, video_id: str = None):
    """Test retrieving context for a query."""
    print(f"\n{'='*60}")
    print(f"RETRIEVAL TEST")
    print(f"{'='*60}")
    print(f"\n  Query: \"{query}\"")
    if video_id:
        print(f"  Filter: video_id={video_id}")

    retriever = ContextRetriever()
    context = retriever.retrieve(
        query=query,
        video_id=video_id,
        top_k=3,
        min_score=0.3,
    )

    print(f"\n  Results found: {context.total_retrieved}")
    print(f"  Best score: {context.best_score:.2%}")

    if context.has_context:
        print(f"\n  Retrieved chunks:")
        for i, (chunk, score, vid) in enumerate(
            zip(context.chunks, context.scores, context.video_ids)
        ):
            print(f"\n  [{i+1}] Score: {score:.2%} | Video: {vid}")
            # Show first 200 chars of chunk
            preview = chunk[:200].replace('\n', ' ')
            print(f"      \"{preview}...\"")

    return context


def show_stats():
    """Show vector store statistics."""
    print(f"\n{'='*60}")
    print("VECTOR STORE STATS")
    print(f"{'='*60}")

    store = get_vector_store()
    stats = store.get_stats()

    print(f"\n  Total chunks: {stats['total_chunks']}")
    print(f"  Indexed videos: {stats['indexed_videos']}")
    print(f"  Collection: {stats['collection_name']}")
    print(f"  Storage: {stats['persist_directory']}")


async def main():
    """Main test function."""
    print("\n" + "="*60)
    print("RAG PIPELINE TEST")
    print("="*60)

    # Get video IDs from command line or use defaults
    video_ids = sys.argv[1:] if len(sys.argv) > 1 else []

    if not video_ids:
        # Use some of the user's recent videos
        video_ids = [
            "Y_coPaZsqxE",  # Top 7 IT Jobs in 2026
            "gQPMGDomsR4",  # Top 7 IT Careers/Jobs in 2026
            "gu_r1VEa5to",  # HOW TO GET JOB IN DUBAI 2026
        ]
        print(f"\n  Using default video IDs: {video_ids}")
        print("  (Pass video IDs as arguments to test specific videos)")

    # Test indexing
    indexed_count = 0
    for video_id in video_ids:
        result = await test_index_video(video_id)
        if result.success and result.chunks_indexed > 0:
            indexed_count += 1

    if indexed_count == 0:
        print("\n  WARNING: No videos were indexed successfully.")
        print("  Some videos may not have transcripts available.")
        show_stats()
        return

    # Show stats after indexing
    show_stats()

    # Test retrieval with sample queries
    test_queries = [
        "What is the salary for IT jobs in Dubai?",
        "How to get a job in UAE?",
        "Best programming languages to learn in 2026",
        "Dubai lo jobs ela vasthayi?",  # Telugu: How to get jobs in Dubai?
        "AI engineer fresher salary",
    ]

    print(f"\n{'='*60}")
    print("TESTING RETRIEVAL WITH SAMPLE QUERIES")
    print(f"{'='*60}")

    for query in test_queries:
        test_retrieval(query)

    # Test with actual unanswered comment
    print(f"\n{'='*60}")
    print("TESTING WITH REAL COMMENT")
    print(f"{'='*60}")

    real_comment = "Bro dubai lo ai engineers ki demand vuntunda as a fresher"
    context = test_retrieval(real_comment)

    print(f"\n  Context quality: {ContextRetriever().check_context_quality(context)}")

    # Show formatted context for LLM
    if context.has_context:
        retriever = ContextRetriever()
        formatted = retriever.format_context_for_llm(context, max_length=1000)
        print(f"\n  Formatted for LLM ({len(formatted)} chars):")
        print(f"  {'-'*50}")
        print(f"  {formatted[:500]}...")

    print(f"\n{'='*60}")
    print("RAG PIPELINE TEST COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())