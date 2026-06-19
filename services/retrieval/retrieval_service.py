# services/retrieval/retrieval_service.py
"""
Hybrid retrieval orchestration: vector search + keyword search, fused via RRF.

Vector and keyword search execute concurrently (each is an independent
PostgreSQL query) via a thread pool. Django manages a separate DB
connection per thread automatically, so this is safe for the lifetime of
a single call. No knowledge graph expansion exists yet — this milestone
returns exactly the RRF top-k chunks with no further expansion.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from services.llm_client.base import EmbeddingClient
from services.retrieval.keyword_search import KeywordSearchResult, keyword_search
from services.retrieval.rrf import DEFAULT_RRF_K, reciprocal_rank_fusion
from services.retrieval.vector_search import VectorSearchResult, vector_search

logger = logging.getLogger("services.retrieval.retrieval_service")

DEFAULT_TOP_K_PER_METHOD = 10
DEFAULT_FINAL_TOP_K = 5


class RetrievalError(Exception):
    """Raised when hybrid retrieval fails."""


@dataclass
class RetrievedChunk:
    """One chunk in the final, fused retrieval result."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    section_identifier: str | None
    chunk_text: str
    retrieval_method: str  # "vector", "keyword", or "hybrid" (found by both)
    retrieval_score: float  # the RRF fused score
    rank: int  # 1-indexed final rank


def retrieve(
    query_text: str,
    embedding_client: EmbeddingClient,
    document_ids: list[uuid.UUID] | None = None,
    top_k_per_method: int = DEFAULT_TOP_K_PER_METHOD,
    final_top_k: int = DEFAULT_FINAL_TOP_K,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[RetrievedChunk]:
    """
    Run hybrid retrieval for a natural-language question.

    Steps:
        1. Embed query_text via embedding_client.
        2. Run vector_search and keyword_search concurrently.
        3. Fuse both ranked lists via Reciprocal Rank Fusion.
        4. Return the top final_top_k fused results with full metadata.

    Raises:
        RetrievalError: if query_text is empty, or embedding/search/fusion fails.
    """
    if not query_text or not query_text.strip():
        raise RetrievalError("query_text must not be empty")

    try:
        query_embedding = embedding_client.embed([query_text])[0]
    except Exception as exc:
        raise RetrievalError(f"Failed to embed query: {exc}") from exc

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            vector_future = executor.submit(
                vector_search, query_embedding, top_k_per_method, document_ids
            )
            keyword_future = executor.submit(
                keyword_search, query_text, top_k_per_method, document_ids
            )
            vector_results = vector_future.result()
            keyword_results = keyword_future.result()
    except Exception as exc:
        raise RetrievalError(f"Hybrid search failed: {exc}") from exc

    vector_metadata = {r.chunk_id: r for r in vector_results}
    keyword_metadata = {r.chunk_id: r for r in keyword_results}

    vector_ranked_ids = [r.chunk_id for r in vector_results]
    keyword_ranked_ids = [r.chunk_id for r in keyword_results]

    try:
        fused = reciprocal_rank_fusion([vector_ranked_ids, keyword_ranked_ids], k=rrf_k)
    except Exception as exc:
        raise RetrievalError(f"RRF fusion failed: {exc}") from exc

    retrieved_chunks: list[RetrievedChunk] = []
    for rank, (chunk_id, fused_score) in enumerate(fused[:final_top_k], start=1):
        in_vector = chunk_id in vector_metadata
        in_keyword = chunk_id in keyword_metadata

        if in_vector and in_keyword:
            method = "hybrid"
            source: VectorSearchResult | KeywordSearchResult = vector_metadata[chunk_id]
        elif in_vector:
            method = "vector"
            source = vector_metadata[chunk_id]
        else:
            method = "keyword"
            source = keyword_metadata[chunk_id]

        retrieved_chunks.append(
            RetrievedChunk(
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                page_number=source.page_number,
                section_identifier=source.section_identifier,
                chunk_text=source.chunk_text,
                retrieval_method=method,
                retrieval_score=fused_score,
                rank=rank,
            )
        )

    logger.info(
        "retrieval_completed query=%r document_ids=%s vector_count=%d keyword_count=%d final_count=%d",
        query_text, document_ids, len(vector_results), len(keyword_results), len(retrieved_chunks),
    )

    return retrieved_chunks