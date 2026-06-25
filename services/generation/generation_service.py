# services/generation/generation_service.py
"""
Orchestrates the full generation pipeline: retrieval -> context assembly ->
generation -> citation validation -> AnswerResult.

generation_client is optional and defaults to the environment-driven
get_generation_client() factory — kept injectable so unit tests never
call a real provider.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from services.generation.citation_validator import Citation, validate_citations
from services.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from services.llm_client.base import EmbeddingClient
from services.llm_client.generation_base import GenerationClient
from services.retrieval.retrieval_service import retrieve

logger = logging.getLogger("services.generation.generation_service")

DEFAULT_TOP_K = 5


@dataclass
class AnswerResult:
    """In-memory result of the generation pipeline. Never persisted."""

    query: str
    answer_text: str
    citations: list[Citation] = field(default_factory=list)
    has_valid_citations: bool = False
    retrieved_chunk_count: int = 0
    rejected_citation_count: int = 0


def _default_generation_client() -> GenerationClient:
    """
    Lazily resolves the environment-configured generation client.

    Deferred import: avoids importing the Gemini SDK (and reading
    GEMINI_API_KEY) unless generate_answer() is called without an
    explicit generation_client — e.g. never, in unit tests that inject
    a fake client.
    """
    from services.llm_client.generation_base import get_generation_client

    return get_generation_client()


def generate_answer(
    query: str,
    document_ids: list[uuid.UUID] | None = None,
    top_k: int = DEFAULT_TOP_K,
    generation_client: GenerationClient | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> AnswerResult:
    """
    Run the full retrieval-to-generation pipeline for a natural-language question.

    If retrieval returns zero chunks, generation is skipped entirely —
    the LLM is never called ungrounded. has_valid_citations is False
    whenever zero citations survive validation, including that empty-
    retrieval case; per project requirements, an uncited answer is a
    failure case, and this flag exists so callers can detect it without
    re-deriving the logic themselves.

    Args:
        query: the natural-language question.
        document_ids: optional filter restricting retrieval to specific
            documents. If None, searches across all READY documents.
        top_k: how many chunks retrieval returns.
        generation_client: a GenerationClient instance. If None, resolved
            via the GENERATION_PROVIDER environment variable.
        embedding_client: passed through to retrieve(). If None, retrieve()
            uses its own default (the local sentence-transformers client).
    """
    retrieved_chunks = retrieve(
        query,
        document_ids=document_ids,
        top_k=top_k,
        embedding_client=embedding_client,
    )

    if not retrieved_chunks:
        logger.info("generation_skipped reason=no_retrieved_chunks query=%r", query)
        return AnswerResult(
            query=query,
            answer_text="",
            citations=[],
            has_valid_citations=False,
            retrieved_chunk_count=0,
            rejected_citation_count=0,
        )

    client = generation_client or _default_generation_client()

    user_prompt = build_user_prompt(query, retrieved_chunks)
    logger.debug("generation_prompt_assembled query=%r user_prompt=%r", query, user_prompt)
    
    answer_text = client.generate(SYSTEM_PROMPT, user_prompt)
    logger.debug("raw_generation_response query=%r answer_text=%r", query, answer_text)

    validation_result = validate_citations(answer_text, retrieved_chunks)

    result = AnswerResult(
        query=query,
        answer_text=answer_text,
        citations=validation_result.citations,
        has_valid_citations=len(validation_result.citations) > 0,
        retrieved_chunk_count=len(retrieved_chunks),
        rejected_citation_count=validation_result.rejected_citation_count,
    )

    if not result.has_valid_citations:
        logger.warning(
            "generation_completed_without_valid_citations query=%r rejected=%d",
            query, validation_result.rejected_citation_count,
        )
    else:
        logger.info(
            "generation_completed query=%r citations=%d rejected=%d",
            query, len(result.citations), validation_result.rejected_citation_count,
        )

    return result