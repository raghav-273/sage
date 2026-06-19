# services/retrieval/retrieval_service.py
"""
Hybrid retrieval orchestration: vector search + keyword search, fused via RRF.

Vector and keyword search execute concurrently via a thread pool — Django
manages a separate DB connection per thread automatically. No knowledge
graph expansion exists yet; this milestone returns exactly the RRF top-k
chunks with no further expansion.

embedding_client is optional and defaults to a lazily-constructed
SentenceTransformerEmbeddingClient (the project's only embedding provider).
Making it an explicit, injectable parameter — rather than hardcoding the
concrete class — is what keeps this module unit-testable without loading
an actual ML model: tests pass a stub EmbeddingClient instead.
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
DEFAULT_TOP_K = 5


class RetrievalError(Exception):
    """Raised when hybrid retrieval fails."""


@dataclass
class RetrievedChunk:
    """One chunk in the final, fused retrieval result."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_text: str
    page_number: int
    section_identifier: str | None
    retrieval_method: str  # "vector", "keyword", or "hybrid" (found by both)
    retrieval_score: float  # the RRF fused score
    rank: int  # 1-indexed final rank


def _default_embedding_client() -> EmbeddingClient:
    """
    Lazily constructs the project's default embedding client.

    Deferred import: avoids loading sentence-transformers (and reading the
    model from disk) unless retrieve() is actually called without an
    explicit embedding_client — e.g. never, in unit tests that inject a stub.
    """
    from services.llm_client.sentence_transformer_client import (
        SentenceTransformerEmbeddingClient,
    )

    return SentenceTransformerEmbeddingClient()


def retrieve(
    query: str,
    document_ids: list[uuid.UUID] | None = None,
    top_k: int = DEFAULT_TOP_K,
    embedding_client: EmbeddingClient | None = None,
    top_k_per_method: int = DEFAULT_TOP_K_PER_METHOD,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[RetrievedChunk]:
    """
    Run hybrid retrieval for a natural-language question.

    Args:
        query: the natural-language question.
        document_ids: optional filter restricting retrieval to specific
            documents. If None, searches across all READY documents.
        top_k: how many fused results to return.
        embedding_client: an EmbeddingClient instance. If None, a
            SentenceTransformerEmbeddingClient is constructed lazily.
        top_k_per_method: how many candidates each individual method
            retrieves before fusion.
        rrf_k: the RRF constant.

    Raises:
        RetrievalError: if query is empty, or embedding/search/fusion fails.
    """
    if not query or not query.strip():
        raise RetrievalError("query must not be empty")

    client = embedding_client or _default_embedding_client()

    try:
        query_embedding = client.embed([query])[0]
    except Exception as exc:
        raise RetrievalError(f"Failed to embed query: {exc}") from exc

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            vector_future = executor.submit(
                vector_search, query_embedding, top_k_per_method, document_ids
            )
            keyword_future = executor.submit(
                keyword_search, query, top_k_per_method, document_ids
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
    for rank, (chunk_id, fused_score) in enumerate(fused[:top_k], start=1):
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
                chunk_text=source.chunk_text,
                page_number=source.page_number,
                section_identifier=source.section_identifier,
                retrieval_method=method,
                retrieval_score=fused_score,
                rank=rank,
            )
        )

    logger.info(
        "retrieval_completed query=%r document_ids=%s vector_count=%d keyword_count=%d final_count=%d",
        query, document_ids, len(vector_results), len(keyword_results), len(retrieved_chunks),
    )

    return retrieved_chunks