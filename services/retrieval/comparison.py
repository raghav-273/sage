# services/retrieval/comparison.py
"""
Retrieval orchestration for cross-document comparison.

Runs two independent retrieve() calls concurrently — one per document.
The embedding is computed once by the shared embedding_client instance;
Django manages separate DB connections per thread automatically.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from services.llm_client.base import EmbeddingClient
from services.retrieval.retrieval_service import RetrievedChunk, retrieve

logger = logging.getLogger("services.retrieval.comparison")

DEFAULT_TOP_K_PER_DOCUMENT = 5


@dataclass
class ComparisonRetrievalResult:
    chunks_a: list[RetrievedChunk]
    chunks_b: list[RetrievedChunk]


def retrieve_for_comparison(
    query: str,
    document_a_id: uuid.UUID,
    document_b_id: uuid.UUID,
    embedding_client: EmbeddingClient | None = None,
    top_k: int = DEFAULT_TOP_K_PER_DOCUMENT,
) -> ComparisonRetrievalResult:
    """
    Retrieves top_k chunks from each document independently and concurrently.

    Accepts document_a_id == document_b_id (degenerate case — the view
    prevents this, but this function handles it gracefully).
    """
    if embedding_client is None:
        from services.llm_client.sentence_transformer_client import (
            SentenceTransformerEmbeddingClient,
        )
        embedding_client = SentenceTransformerEmbeddingClient()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(
            retrieve, query, [document_a_id], top_k, embedding_client
        )
        future_b = executor.submit(
            retrieve, query, [document_b_id], top_k, embedding_client
        )
        chunks_a = future_a.result()
        chunks_b = future_b.result()

    logger.info(
        "comparison_retrieval_completed query=%r doc_a=%s chunks=%d doc_b=%s chunks=%d",
        query, document_a_id, len(chunks_a), document_b_id, len(chunks_b),
    )

    return ComparisonRetrievalResult(chunks_a=chunks_a, chunks_b=chunks_b)