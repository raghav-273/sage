# services/retrieval/vector_search.py
"""
Exact pgvector cosine similarity search.

No ANN index (IVFFlat/HNSW) is used — pgvector's <=> operator performs a
sequential scan against every embedded chunk in scope. Dataset size is
small enough for exact search to remain fast and accurate.

Retrieval is restricted to chunks belonging to Document rows with
status=READY — chunks from documents still mid-ingestion are never
returned, even if their embedding has already been populated.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from pgvector.django import CosineDistance

logger = logging.getLogger("services.retrieval.vector_search")


class VectorSearchError(Exception):
    """Raised when vector search cannot be executed."""


@dataclass
class VectorSearchResult:
    """One chunk returned by vector search, with its similarity score."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    section_identifier: str | None
    chunk_text: str
    score: float  # cosine similarity; 1.0 = identical
    rank: int  # 1-indexed rank within this result list


def vector_search(
    query_embedding: list[float],
    top_k: int = 10,
    document_ids: list[uuid.UUID] | None = None,
) -> list[VectorSearchResult]:
    """
    Run exact cosine similarity search against ContentChunk.embedding.

    Args:
        query_embedding: the question's embedding vector. Must match
            settings.PGVECTOR_EMBEDDING_DIMENSIONS in length.
        top_k: maximum number of results to return.
        document_ids: optional filter restricting search to specific
            documents. If None, searches across all READY documents.

    Returns:
        Results ordered by descending similarity (rank 1 = most similar).
        Chunks with a NULL embedding are never returned.

    Raises:
        VectorSearchError: if the query fails (e.g. dimension mismatch).
    """
    from django.conf import settings

    from apps.chunks.models import ContentChunk
    from apps.documents.models import Document

    if len(query_embedding) != settings.PGVECTOR_EMBEDDING_DIMENSIONS:
        raise VectorSearchError(
            f"query_embedding has {len(query_embedding)} dimensions; "
            f"expected {settings.PGVECTOR_EMBEDDING_DIMENSIONS}"
        )

    queryset = ContentChunk.objects.filter(
        document__status=Document.Status.READY,
        embedding__isnull=False,
    )
    if document_ids:
        queryset = queryset.filter(document_id__in=document_ids)

    try:
        queryset = (
            queryset.select_related("page")
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:top_k]
        )
        chunks = list(queryset)
    except Exception as exc:
        raise VectorSearchError(f"Vector search query failed: {exc}") from exc

    results = [
        VectorSearchResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            page_number=chunk.page.page_number,
            section_identifier=chunk.section_identifier,
            chunk_text=chunk.chunk_text,
            score=1.0 - chunk.distance,
            rank=rank,
        )
        for rank, chunk in enumerate(chunks, start=1)
    ]

    logger.info(
        "vector_search_completed top_k=%d document_ids=%s results=%d",
        top_k, document_ids, len(results),
    )

    return results