"""RAG (Retrieval Augmented Generation) module."""

from src.rag.embeddings import EmbeddingService, get_embedding_service
from src.rag.vector_store import VectorStore, get_vector_store
from src.rag.indexer import TranscriptIndexer, IndexResult, get_indexer
from src.rag.retriever import ContextRetriever, RetrievedContext, get_retriever

__all__ = [
    # Embeddings
    "EmbeddingService",
    "get_embedding_service",
    # Vector Store
    "VectorStore",
    "get_vector_store",
    # Indexer
    "TranscriptIndexer",
    "IndexResult",
    "get_indexer",
    # Retriever
    "ContextRetriever",
    "RetrievedContext",
    "get_retriever",
]