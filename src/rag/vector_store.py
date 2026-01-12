"""
ChromaDB vector store for transcript storage and retrieval.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any

import chromadb
from chromadb.config import Settings as ChromaSettings
import structlog

from src.config import get_chroma_settings
from src.rag.embeddings import get_embedding_service

logger = structlog.get_logger(__name__)


class VectorStore:
    """
    ChromaDB-based vector store for video transcript chunks.

    Supports:
    - Adding transcript chunks with metadata
    - Semantic similarity search
    - Filtering by video_id
    - Persistent storage
    """

    def __init__(
        self,
        collection_name: str = None,
        persist_directory: str = None,
    ):
        settings = get_chroma_settings()
        self.collection_name = collection_name or settings.collection_name
        self.persist_directory = persist_directory or settings.persist_directory

        # Ensure persist directory exists
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

        self._client = None
        self._collection = None
        self._embedding_service = get_embedding_service()

    @property
    def client(self) -> chromadb.Client:
        """Lazy load ChromaDB client."""
        if self._client is None:
            logger.info(
                "initializing_chromadb",
                persist_directory=self.persist_directory,
            )
            self._client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self) -> chromadb.Collection:
        """Get or create the collection."""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "YouTube video transcript chunks"},
            )
            logger.info(
                "collection_ready",
                name=self.collection_name,
                count=self._collection.count(),
            )
        return self._collection

    def add_chunks(
        self,
        chunks: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> int:
        """
        Add transcript chunks to the vector store.

        Args:
            chunks: List of text chunks
            metadatas: List of metadata dicts for each chunk
            ids: Optional list of unique IDs (auto-generated if not provided)

        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0

        # Generate IDs if not provided
        if ids is None:
            ids = [
                f"{meta.get('video_id', 'unknown')}_{meta.get('chunk_index', i)}"
                for i, meta in enumerate(metadatas)
            ]

        # Generate embeddings
        embeddings = self._embedding_service.embed_texts(chunks)

        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )

        logger.info(
            "chunks_added",
            count=len(chunks),
            video_id=metadatas[0].get("video_id") if metadatas else None,
        )

        return len(chunks)

    def search(
        self,
        query: str,
        n_results: int = 5,
        video_id: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks.

        Args:
            query: Search query text
            n_results: Maximum number of results
            video_id: Optional filter by video ID
            min_score: Minimum similarity score (0-1)

        Returns:
            List of results with text, metadata, and score
        """
        # Build where filter
        where_filter = None
        if video_id:
            where_filter = {"video_id": video_id}

        # Generate query embedding
        query_embedding = self._embedding_service.embed_text(query)

        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # Format results
        formatted = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                # ChromaDB returns distance, convert to similarity score
                distance = results["distances"][0][i]
                # For L2 distance, convert to similarity (1 / (1 + distance))
                score = 1 / (1 + distance)

                if score >= min_score:
                    formatted.append({
                        "text": doc,
                        "metadata": results["metadatas"][0][i],
                        "score": score,
                    })

        logger.debug(
            "search_completed",
            query_length=len(query),
            results_count=len(formatted),
        )

        return formatted

    def get_video_chunks(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific video.

        Args:
            video_id: YouTube video ID

        Returns:
            List of chunks with metadata
        """
        results = self.collection.get(
            where={"video_id": video_id},
            include=["documents", "metadatas"],
        )

        chunks = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                chunks.append({
                    "text": doc,
                    "metadata": results["metadatas"][i],
                })

        return chunks

    def delete_video(self, video_id: str) -> int:
        """
        Delete all chunks for a video.

        Args:
            video_id: YouTube video ID

        Returns:
            Number of chunks deleted
        """
        # Get existing chunks
        existing = self.collection.get(
            where={"video_id": video_id},
            include=[],
        )

        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
            logger.info("video_deleted", video_id=video_id, chunks=len(existing["ids"]))
            return len(existing["ids"])

        return 0

    def video_exists(self, video_id: str) -> bool:
        """Check if a video has been indexed."""
        results = self.collection.get(
            where={"video_id": video_id},
            limit=1,
            include=[],
        )
        return len(results["ids"]) > 0

    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics."""
        total_chunks = self.collection.count()

        # Get unique video count (sample approach)
        sample = self.collection.get(
            limit=10000,
            include=["metadatas"],
        )

        video_ids = set()
        if sample["metadatas"]:
            for meta in sample["metadatas"]:
                if meta and "video_id" in meta:
                    video_ids.add(meta["video_id"])

        return {
            "total_chunks": total_chunks,
            "indexed_videos": len(video_ids),
            "collection_name": self.collection_name,
            "persist_directory": self.persist_directory,
        }


# Singleton instance
_vector_store = None


def get_vector_store() -> VectorStore:
    """Get the singleton vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store