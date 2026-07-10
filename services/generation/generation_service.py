# services/generation/generation_service.py
"""
Orchestrates the full generation pipeline: retrieval -> context assembly ->
generation -> citation validation -> AnswerResult.

generation_client is optional and defaults to the environment-driven
get_generation_client() factory — kept injectable so unit tests never
call a real provider.
"""

from __future__ import annotations
import re as _re
import logging
import uuid
import re as _re_comparison 
from dataclasses import dataclass as _dataclass
from dataclasses import dataclass, field



from services.generation.citation_validator import Citation, validate_citations
from services.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from services.llm_client.base import EmbeddingClient
from services.llm_client.generation_base import GenerationClient
from services.retrieval.retrieval_service import retrieve

from services.generation.prompts import (
    CONVERSATIONAL_SYSTEM_PROMPT, SYSTEM_PROMPT, build_conversational_user_prompt, build_user_prompt,
)

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
    prior_turns: list[tuple[str, str]] | None = None,
) -> AnswerResult:
    """
    ... (existing docstring, plus:)

    prior_turns: optional (query, answer) pairs from earlier in a
        conversation, oldest first. When provided, both the system
        prompt and user prompt switch to the conversational variants
        (see services.generation.prompts) so the model can resolve
        follow-up references. Every existing caller omits this and is
        completely unaffected.
    """
    retrieved_chunks = retrieve(
        query, document_ids=document_ids, top_k=top_k, embedding_client=embedding_client,
    )

    if not retrieved_chunks:
        logger.info("generation_skipped reason=no_retrieved_chunks query=%r", query)
        return AnswerResult(
            query=query, answer_text="", citations=[],
            has_valid_citations=False, retrieved_chunk_count=0, rejected_citation_count=0,
        )

    client = generation_client or _default_generation_client()

    if prior_turns:
        system_prompt = CONVERSATIONAL_SYSTEM_PROMPT
        user_prompt = build_conversational_user_prompt(query, retrieved_chunks, prior_turns)
    else:
        system_prompt = SYSTEM_PROMPT
        user_prompt = build_user_prompt(query, retrieved_chunks)

    logger.debug("generation_prompt_assembled query=%r user_prompt=%r", query, user_prompt)
    answer_text = client.generate(system_prompt, user_prompt)
    logger.debug("raw_generation_response query=%r answer_text=%r", query, answer_text)

    validation_result = validate_citations(answer_text, retrieved_chunks)

    result = AnswerResult(
        query=query, answer_text=answer_text, citations=validation_result.citations,
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


@dataclass
class ComplianceResult:
    """In-memory result of a compliance verification query. Never persisted."""

    requirement: str
    verdict: str           # "COMPLIANT" | "NON-COMPLIANT" | "INSUFFICIENT EVIDENCE"
    answer_text: str       # raw LLM output with [CITE:] markers
    rendered_answer: str   # [CITE:] markers replaced with [n] numbers
    citations: list
    has_valid_citations: bool
    retrieved_chunk_count: int
    rejected_citation_count: int

    @property
    def verdict_class(self) -> str:
        """CSS class aligned with the existing three-state confidence system."""
        return {
            "COMPLIANT": "badge-verified",
            "NON-COMPLIANT": "badge-not-found",
            "INSUFFICIENT EVIDENCE": "badge-unverified",
        }.get(self.verdict, "badge-unverified")

    @property
    def verdict_icon(self) -> str:
        return {
            "COMPLIANT": "✓",
            "NON-COMPLIANT": "✗",
            "INSUFFICIENT EVIDENCE": "⚠",
        }.get(self.verdict, "⚠")


def _parse_comparison_sections(text: str) -> dict[str, str]:
    """
    Parses ## Section headers from LLM comparison output into a dict.
    Keys are section titles; values are the section body text.
    Any text before the first ## header is stored under key "Preamble".
    """
    header_pattern = _re_comparison.compile(r"^##\s+(.+)$", _re_comparison.MULTILINE)
    matches = list(header_pattern.finditer(text))

    if not matches:
        return {"Analysis": text.strip()}

    result: dict[str, str] = {}

    preamble = text[: matches[0].start()].strip()
    if preamble:
        result["Preamble"] = preamble

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        result[title] = content

    return result


@dataclass
class ComparisonResult:
    """In-memory result of a cross-document comparison. Never persisted."""

    query: str
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    document_a_name: str
    document_b_name: str
    answer_text: str       # raw with [CITE:uuid] markers
    rendered_answer: str   # markers replaced with [n]
    citations: list
    has_valid_citations: bool
    retrieved_count_a: int
    retrieved_count_b: int
    rejected_citation_count: int

    @property
    def sections(self) -> dict[str, str]:
        """Answer split into the four comparison sections for template rendering."""
        return _parse_comparison_sections(self.rendered_answer)


def generate_comparison_answer(
    query: str,
    document_a_id: uuid.UUID,
    document_b_id: uuid.UUID,
    generation_client: GenerationClient | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> ComparisonResult:
    """
    Cross-document comparison: retrieves relevant chunks from each document
    independently, then generates a structured AGREEMENT / CONFLICT /
    EXCLUSIVE comparison with per-document, per-clause citations.
    """
    from apps.documents.models import Document as _Doc
    from services.generation.answer_rendering import (
        render_answer_with_numbered_citations,
    )
    from services.generation.prompts import (
        COMPARISON_SYSTEM_PROMPT,
        build_comparison_user_prompt,
    )
    from services.retrieval.comparison import retrieve_for_comparison

    try:
        doc_a = _Doc.objects.get(id=document_a_id)
        doc_b = _Doc.objects.get(id=document_b_id)
    except _Doc.DoesNotExist as exc:
        raise GenerationError(f"Document not found: {exc}") from exc

    retrieval = retrieve_for_comparison(
        query=query,
        document_a_id=document_a_id,
        document_b_id=document_b_id,
        embedding_client=embedding_client,
    )

    user_prompt = build_comparison_user_prompt(
        query,
        retrieval.chunks_a, doc_a.name,
        retrieval.chunks_b, doc_b.name,
    )

    client = generation_client or _default_generation_client()
    logger.debug("comparison_prompt_assembled query=%r", query)
    answer_text = client.generate(COMPARISON_SYSTEM_PROMPT, user_prompt)
    logger.debug("comparison_raw_response query=%r answer=%r", query, answer_text)

    all_chunks = retrieval.chunks_a + retrieval.chunks_b
    validation_result = validate_citations(answer_text, all_chunks)

    # Reuse render_answer_with_numbered_citations via a temporary AnswerResult
    temp = AnswerResult(
        query=query,
        answer_text=answer_text,
        citations=validation_result.citations,
        has_valid_citations=bool(validation_result.citations),
        retrieved_chunk_count=len(all_chunks),
        rejected_citation_count=validation_result.rejected_citation_count,
    )
    rendered_answer = render_answer_with_numbered_citations(temp)

    result = ComparisonResult(
        query=query,
        document_a_id=document_a_id,
        document_b_id=document_b_id,
        document_a_name=doc_a.name,
        document_b_name=doc_b.name,
        answer_text=answer_text,
        rendered_answer=rendered_answer,
        citations=validation_result.citations,
        has_valid_citations=bool(validation_result.citations),
        retrieved_count_a=len(retrieval.chunks_a),
        retrieved_count_b=len(retrieval.chunks_b),
        rejected_citation_count=validation_result.rejected_citation_count,
    )

    logger.info(
        "comparison_completed query=%r doc_a=%s doc_b=%s citations=%d",
        query, doc_a.name, doc_b.name, len(result.citations),
    )
    return result



_VERDICT_PATTERN = _re.compile(
    r"^VERDICT:\s*(COMPLIANT|NON-COMPLIANT|INSUFFICIENT EVIDENCE)",
    _re.MULTILINE,
)

def generate_compliance_answer(
    requirement: str,
    document_ids: list[uuid.UUID] | None = None,
    generation_client: GenerationClient | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> ComplianceResult:
    """
    Runs compliance verification: retrieves relevant clauses, generates a
    COMPLIANT / NON-COMPLIANT / INSUFFICIENT EVIDENCE verdict with citations.

    Reuses the full retrieval → generation → citation-validation pipeline.
    Only the system prompt and result type differ from generate_answer().
    """
    from services.generation.answer_rendering import render_answer_with_numbered_citations
    from services.generation.prompts import (
        COMPLIANCE_SYSTEM_PROMPT, build_compliance_user_prompt,
    )

    retrieved_chunks = retrieve(
        requirement,
        document_ids=document_ids,
        top_k=DEFAULT_TOP_K,
        embedding_client=embedding_client,
    )

    if not retrieved_chunks:
        logger.info(
            "compliance_generation_skipped reason=no_retrieved_chunks requirement=%r",
            requirement,
        )
        return ComplianceResult(
            requirement=requirement,
            verdict="INSUFFICIENT EVIDENCE",
            answer_text="",
            rendered_answer="No relevant clauses were found in the selected documents.",
            citations=[],
            has_valid_citations=False,
            retrieved_chunk_count=0,
            rejected_citation_count=0,
        )

    client = generation_client or _default_generation_client()
    user_prompt = build_compliance_user_prompt(requirement, retrieved_chunks)

    logger.debug(
        "compliance_prompt_assembled requirement=%r prompt=%r", requirement, user_prompt
    )
    answer_text = client.generate(COMPLIANCE_SYSTEM_PROMPT, user_prompt)
    logger.debug("compliance_raw_response requirement=%r answer=%r", requirement, answer_text)

    verdict_match = _VERDICT_PATTERN.search(answer_text)
    verdict = verdict_match.group(1) if verdict_match else "INSUFFICIENT EVIDENCE"

    validation_result = validate_citations(answer_text, retrieved_chunks)

    temp_result = AnswerResult(
        query=requirement,
        answer_text=answer_text,
        citations=validation_result.citations,
        has_valid_citations=len(validation_result.citations) > 0,
        retrieved_chunk_count=len(retrieved_chunks),
        rejected_citation_count=validation_result.rejected_citation_count,
    )
    rendered_answer = render_answer_with_numbered_citations(temp_result)

    result = ComplianceResult(
        requirement=requirement,
        verdict=verdict,
        answer_text=answer_text,
        rendered_answer=rendered_answer,
        citations=validation_result.citations,
        has_valid_citations=len(validation_result.citations) > 0,
        retrieved_chunk_count=len(retrieved_chunks),
        rejected_citation_count=validation_result.rejected_citation_count,
    )

    logger.info(
        "compliance_completed requirement=%r verdict=%s citations=%d",
        requirement, verdict, len(result.citations),
    )
    return result