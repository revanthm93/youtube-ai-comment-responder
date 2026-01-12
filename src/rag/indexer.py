"""
Transcript indexer for RAG pipeline.

Fetches video transcripts and indexes them in the vector store.
"""

from dataclasses import dataclass
from typing import List, Optional

import structlog

from src.youtube.transcript import TranscriptFetcher, TranscriptFetchError
from src.rag.vector_store import get_vector_store, VectorStore

logger = structlog.get_logger(__name__)


@dataclass
class IndexResult:
    """Result of indexing a video."""

    video_id: str
    success: bool
    chunks_indexed: int = 0
    language: Optional[str] = None
    error: Optional[str] = None


class TranscriptIndexer:
    """
    Indexes YouTube video transcripts for RAG retrieval.

    Handles:
    - Fetching transcripts (Telugu/English)
    - Chunking for optimal retrieval
    - Storing in vector database
    """

    def __init__(
        self,
        vector_store: VectorStore = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        self.vector_store = vector_store or get_vector_store()
        self.transcript_fetcher = TranscriptFetcher()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def index_video(
        self,
        video_id: str,
        video_title: Optional[str] = None,
        force_reindex: bool = False,
    ) -> IndexResult:
        """
        Index a single video's transcript.

        Args:
            video_id: YouTube video ID
            video_title: Optional video title for metadata
            force_reindex: If True, re-index even if already exists

        Returns:
            IndexResult with status and chunk count
        """
        # Check if already indexed
        if not force_reindex and self.vector_store.video_exists(video_id):
            logger.info("video_already_indexed", video_id=video_id)
            return IndexResult(
                video_id=video_id,
                success=True,
                chunks_indexed=0,
                error="Already indexed (use force_reindex=True to re-index)",
            )

        # Delete existing chunks if re-indexing
        if force_reindex:
            self.vector_store.delete_video(video_id)

        try:
            # Fetch transcript chunks
            chunks = await self.transcript_fetcher.get_transcript_chunks(
                video_id,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )

            if not chunks:
                return IndexResult(
                    video_id=video_id,
                    success=False,
                    error="No transcript chunks generated",
                )

            # Prepare for indexing
            texts = []
            metadatas = []
            language = None

            for chunk_text, metadata in chunks:
                texts.append(chunk_text)

                # Enrich metadata
                metadata["video_title"] = video_title or ""
                metadatas.append(metadata)

                if language is None:
                    language = metadata.get("language")

            # Index chunks
            indexed_count = self.vector_store.add_chunks(texts, metadatas)

            logger.info(
                "video_indexed",
                video_id=video_id,
                chunks=indexed_count,
                language=language,
            )

            return IndexResult(
                video_id=video_id,
                success=True,
                chunks_indexed=indexed_count,
                language=language,
            )

        except TranscriptFetchError as e:
            logger.warning("transcript_fetch_failed", video_id=video_id, error=str(e))
            return IndexResult(
                video_id=video_id,
                success=False,
                error=str(e),
            )

        except Exception as e:
            logger.error("indexing_failed", video_id=video_id, error=str(e))
            return IndexResult(
                video_id=video_id,
                success=False,
                error=f"Indexing failed: {e}",
            )

    async def index_videos(
        self,
        video_ids: List[str],
        force_reindex: bool = False,
    ) -> List[IndexResult]:
        """
        Index multiple videos.

        Args:
            video_ids: List of YouTube video IDs
            force_reindex: If True, re-index even if already exists

        Returns:
            List of IndexResult for each video
        """
        results = []
        for video_id in video_ids:
            result = await self.index_video(video_id, force_reindex=force_reindex)
            results.append(result)

        # Summary logging
        success_count = sum(1 for r in results if r.success)
        total_chunks = sum(r.chunks_indexed for r in results)

        logger.info(
            "batch_indexing_complete",
            total_videos=len(video_ids),
            successful=success_count,
            total_chunks=total_chunks,
        )

        return results

    def get_indexing_stats(self) -> dict:
        """Get statistics about indexed content."""
        return self.vector_store.get_stats()


# Singleton instance
_indexer = None


def get_indexer() -> TranscriptIndexer:
    """Get the singleton indexer instance."""
    global _indexer
    if _indexer is None:
        _indexer = TranscriptIndexer()
    return _indexer