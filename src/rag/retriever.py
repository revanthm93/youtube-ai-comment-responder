"""
Retrieval service for RAG pipeline.

Retrieves relevant transcript chunks for comment response generation.
"""

from dataclasses import dataclass
from typing import List, Optional

import structlog

from src.config import get_response_settings
from src.rag.vector_store import get_vector_store, VectorStore

logger = structlog.get_logger(__name__)


@dataclass
class RetrievedContext:
    """Retrieved context for response generation."""

    chunks: List[str]
    scores: List[float]
    video_ids: List[str]
    total_retrieved: int
    query: str

    @property
    def has_context(self) -> bool:
        """Check if any context was retrieved."""
        return len(self.chunks) > 0

    @property
    def combined_context(self) -> str:
        """Combine all chunks into a single context string."""
        if not self.chunks:
            return ""
        return "\n\n---\n\n".join(self.chunks)

    @property
    def best_score(self) -> float:
        """Get the highest similarity score."""
        return max(self.scores) if self.scores else 0.0


class ContextRetriever:
    """
    Retrieves relevant video transcript context for comment responses.

    Features:
    - Semantic search across all indexed videos
    - Optional filtering by specific video
    - Configurable similarity threshold
    - Context ranking and selection
    """

    def __init__(
        self,
        vector_store: VectorStore = None,
        default_top_k: int = 3,
    ):
        self.vector_store = vector_store or get_vector_store()
        self.settings = get_response_settings()
        self.default_top_k = default_top_k

    def retrieve(
        self,
        query: str,
        video_id: Optional[str] = None,
        top_k: int = None,
        min_score: float = None,
    ) -> RetrievedContext:
        """
        Retrieve relevant context for a query.

        Args:
            query: The search query (usually comment text)
            video_id: Optional - limit search to specific video
            top_k: Number of chunks to retrieve
            min_score: Minimum similarity score threshold

        Returns:
            RetrievedContext with relevant chunks
        """
        top_k = top_k or self.default_top_k
        min_score = min_score or self.settings.tier2_similarity_threshold

        # Search vector store
        results = self.vector_store.search(
            query=query,
            n_results=top_k,
            video_id=video_id,
            min_score=min_score,
        )

        # Extract data from results
        chunks = [r["text"] for r in results]
        scores = [r["score"] for r in results]
        video_ids = [r["metadata"].get("video_id", "unknown") for r in results]

        context = RetrievedContext(
            chunks=chunks,
            scores=scores,
            video_ids=video_ids,
            total_retrieved=len(results),
            query=query,
        )

        logger.debug(
            "context_retrieved",
            query_length=len(query),
            chunks_found=len(chunks),
            best_score=context.best_score,
            video_id=video_id,
        )

        return context

    def retrieve_for_comment(
        self,
        comment_text: str,
        video_id: str,
        include_other_videos: bool = True,
    ) -> RetrievedContext:
        """
        Retrieve context specifically for responding to a comment.

        Prioritizes content from the same video, but can include
        related content from other videos if needed.

        Args:
            comment_text: The comment to respond to
            video_id: The video the comment is on
            include_other_videos: Whether to search other videos too

        Returns:
            RetrievedContext optimized for comment response
        """
        # First, try to get context from the same video
        same_video_context = self.retrieve(
            query=comment_text,
            video_id=video_id,
            top_k=3,
        )

        if same_video_context.has_context and same_video_context.best_score > 0.7:
            # Good context from same video
            logger.debug(
                "using_same_video_context",
                video_id=video_id,
                chunks=len(same_video_context.chunks),
            )
            return same_video_context

        if include_other_videos:
            # Search across all videos
            all_video_context = self.retrieve(
                query=comment_text,
                video_id=None,  # Search all
                top_k=5,
            )

            if all_video_context.has_context:
                logger.debug(
                    "using_cross_video_context",
                    video_ids=list(set(all_video_context.video_ids)),
                    chunks=len(all_video_context.chunks),
                )
                return all_video_context

        # Return whatever we found from same video
        return same_video_context

    def check_context_quality(self, context: RetrievedContext) -> str:
        """
        Assess the quality of retrieved context.

        Returns:
            'high', 'medium', 'low', or 'none'
        """
        if not context.has_context:
            return "none"

        best = context.best_score
        avg = sum(context.scores) / len(context.scores)

        if best > 0.8 and avg > 0.7:
            return "high"
        elif best > 0.6 and avg > 0.5:
            return "medium"
        elif best > 0.4:
            return "low"
        else:
            return "none"

    def format_context_for_llm(
        self,
        context: RetrievedContext,
        max_length: int = 2000,
    ) -> str:
        """
        Format retrieved context for LLM prompt.

        Args:
            context: Retrieved context
            max_length: Maximum character length

        Returns:
            Formatted context string
        """
        if not context.has_context:
            return ""

        formatted_parts = []
        current_length = 0

        for i, (chunk, score, vid) in enumerate(
            zip(context.chunks, context.scores, context.video_ids)
        ):
            # Format chunk with metadata
            part = f"[Relevance: {score:.0%}]\n{chunk}"

            if current_length + len(part) > max_length:
                # Truncate if needed
                remaining = max_length - current_length
                if remaining > 100:
                    part = part[:remaining] + "..."
                    formatted_parts.append(part)
                break

            formatted_parts.append(part)
            current_length += len(part) + 10  # Account for separators

        return "\n\n---\n\n".join(formatted_parts)


# Singleton instance
_retriever = None


def get_retriever() -> ContextRetriever:
    """Get the singleton retriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = ContextRetriever()
    return _retriever