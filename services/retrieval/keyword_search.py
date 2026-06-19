# services/retrieval/keyword_search.py
"""
PostgreSQL full-text search using Django's SearchVector/SearchQuery/SearchRank.

The tsvector is computed on the fly via SearchVector('chunk_text') rather
than read from a stored, indexed column — no GIN index exists yet. This is
correct at MVP collection sizes; a stored tsvector column with a GIN index
is a purely additive future migration if full-text query latency becomes
a bottleneck.

Retrieval is restricted to chunks belonging to Document rows with
status=READY, mirroring vector_search.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

logger = logging.getLogger("services.retrieval.keyword_search")


class KeywordSearchError(Exception):
    """Raised when keyword search cannot be executed."""


@dataclass
class KeywordSearchResult:
    """One chunk returned by keyword search, with its rank score."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    section_identifier: str | None
    chunk_text: str
    score: float  # ts_rank score; not bounded to [0, 1]
    rank: int  # 1-indexed rank within this result list


def keyword_search(
    query_text: str,
    top_k: int = 10,
    document_ids: list[uuid.UUID] | None = None,
) -> list[KeywordSearchResult]:
    """
    Run PostgreSQL full-text search against ContentChunk.chunk_text.

    Args:
        query_text: the raw natural-language question.
        top_k: maximum number of results to return.
        document_ids: optional filter restricting search to specific
            documents. If None, searches across all READY documents.

    Returns:
        Results ordered by descending ts_rank. Chunks with no matching
        terms are excluded (search_rank__gt=0).

    Raises:
        KeywordSearchError: if query_text is empty or the query fails.
    """
    from apps.chunks.models import ContentChunk
    from apps.documents.models import Document

    if not query_text or not query_text.strip():
        raise KeywordSearchError("query_text must not be empty")

    queryset = ContentChunk.objects.filter(document__status=Document.Status.READY)
    if document_ids:
        queryset = queryset.filter(document_id__in=document_ids)

    search_query = SearchQuery(query_text, search_type="plain", config="english")

    try:
        queryset = (
            queryset.select_related("page")
            .annotate(
                search_rank=SearchRank(
                    SearchVector("chunk_text", config="english"), search_query
                )
            )
            .filter(search_rank__gt=0)
            .order_by("-search_rank")[:top_k]
        )
        chunks = list(queryset)
    except Exception as exc:
        raise KeywordSearchError(f"Keyword search query failed: {exc}") from exc

    results = [
        KeywordSearchResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            page_number=chunk.page.page_number,
            section_identifier=chunk.section_identifier,
            chunk_text=chunk.chunk_text,
            score=chunk.search_rank,
            rank=rank,
        )
        for rank, chunk in enumerate(chunks, start=1)
    ]

    logger.info(
        "keyword_search_completed query=%r top_k=%d document_ids=%s results=%d",
        query_text, top_k, document_ids, len(results),
    )

    return results