"""
Embedding service for generating text embeddings.

Uses sentence-transformers for local embedding generation.
"""

from typing import List

import structlog
from sentence_transformers import SentenceTransformer

from src.config import get_settings

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """
    Service for generating text embeddings using sentence-transformers.

    Uses all-MiniLM-L6-v2 by default - fast and good quality for semantic search.
    """

    def __init__(self, model_name: str = None):
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self._model = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy load the embedding model."""
        if self._model is None:
            logger.info("loading_embedding_model", model=self.model_name)
            self._model = SentenceTransformer(self.model_name)
            logger.info("embedding_model_loaded", model=self.model_name)
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        logger.debug("embedding_texts", count=len(texts))
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model."""
        return self.model.get_sentence_embedding_dimension()


# Singleton instance
_embedding_service = None


def get_embedding_service() -> EmbeddingService:
    """Get the singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service