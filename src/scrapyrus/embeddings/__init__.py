"""Unified storage and retrieval of keyword and XML content embeddings."""

from scrapyrus.embeddings.clients import build_embedding_client
from scrapyrus.embeddings.corpora import EMBEDDING_CORPORA, DocumentMatch, KeywordMatch
from scrapyrus.embeddings.schema import (
    EmbeddingModelMismatchError,
    EmbeddingTableMetadata,
    EmbeddingsUnavailableError,
    PgvectorUnavailableError,
    SourceUnavailableError,
)
from scrapyrus.embeddings.store import EmbeddingSpecification, EmbeddingStore

__all__ = [
    "EMBEDDING_CORPORA",
    "DocumentMatch",
    "KeywordMatch",
    "EmbeddingSpecification",
    "EmbeddingStore",
    "EmbeddingModelMismatchError",
    "EmbeddingTableMetadata",
    "EmbeddingsUnavailableError",
    "PgvectorUnavailableError",
    "SourceUnavailableError",
    "build_embedding_client",
]
