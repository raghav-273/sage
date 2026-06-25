# services/generation/citation_validator.py
"""
Parses [CITE:chunk_id] markers from generated text and validates them
against the actual set of retrieved chunks.

This is the core hallucination-prevention mechanism: the prompt instructs
the model to only cite provided chunk_ids, but this module is what
actually enforces it. Any marker whose chunk_id doesn't match a chunk
that was genuinely in context is rejected — it never reaches the caller
as a valid citation.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from services.retrieval.retrieval_service import RetrievedChunk

logger = logging.getLogger("services.generation.citation_validator")

# Matches [CITE:<36 hex/hyphen characters>]. The character count matches a
# standard UUID string's length; final validity is checked via uuid.UUID()
# below, so a malformed-but-right-length string is rejected, not raised on.
CITATION_MARKER_PATTERN = re.compile(r"\[CITE:\s*([0-9a-fA-F-]{36})\]")


@dataclass
class Citation:
    """One validated citation, ready to attach to an AnswerResult."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    section_identifier: str | None
    excerpt: str
    confidence_score: float
    retrieval_method: str


@dataclass
class CitationValidationResult:
    """Output of validating all citation markers in a generated answer."""

    citations: list[Citation]
    rejected_citation_count: int


def validate_citations(
    answer_text: str,
    retrieved_chunks: list[RetrievedChunk],
) -> CitationValidationResult:
    """
    Parses every [CITE:chunk_id] marker in answer_text and validates each
    against retrieved_chunks — the only chunks genuinely available to the
    model.

    Markers referencing a chunk_id not present in retrieved_chunks, or not
    a well-formed UUID, are rejected: logged and excluded from the
    returned citations list. Duplicate citations of an already-validated
    chunk_id are deduplicated (one Citation per unique chunk_id), not
    counted as rejections.
    """
    chunk_lookup: dict[uuid.UUID, RetrievedChunk] = {c.chunk_id: c for c in retrieved_chunks}

    citations: list[Citation] = []
    seen_chunk_ids: set[uuid.UUID] = set()
    rejected_count = 0

    for match in CITATION_MARKER_PATTERN.finditer(answer_text):
        raw_id = match.group(1)

        try:
            chunk_id = uuid.UUID(raw_id)
        except ValueError:
            logger.warning("citation_rejected reason=malformed_uuid raw=%r", raw_id)
            rejected_count += 1
            continue

        if chunk_id not in chunk_lookup:
            logger.warning("citation_rejected reason=unknown_chunk_id chunk_id=%s", chunk_id)
            rejected_count += 1
            continue

        if chunk_id in seen_chunk_ids:
            continue  # duplicate of an already-validated citation, not a rejection

        seen_chunk_ids.add(chunk_id)
        source = chunk_lookup[chunk_id]
        citations.append(
            Citation(
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                page_number=source.page_number,
                section_identifier=source.section_identifier,
                excerpt=source.chunk_text,
                confidence_score=source.retrieval_score,
                retrieval_method=source.retrieval_method,
            )
        )

    return CitationValidationResult(citations=citations, rejected_citation_count=rejected_count)