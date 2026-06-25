# tests/unit/test_citation_validator.py
"""Unit tests for services.generation.citation_validator. Pure logic — no database needed."""

from __future__ import annotations

import unittest
import uuid

from services.generation.citation_validator import validate_citations
from services.retrieval.retrieval_service import RetrievedChunk


def _make_chunk(
    chunk_id: uuid.UUID | None = None,
    page_number: int = 1,
    section_identifier: str | None = "4.1",
    chunk_text: str = "sample chunk text",
    retrieval_method: str = "hybrid",
    retrieval_score: float = 0.9,
    rank: int = 1,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_text=chunk_text,
        page_number=page_number,
        section_identifier=section_identifier,
        retrieval_method=retrieval_method,
        retrieval_score=retrieval_score,
        rank=rank,
    )


class ValidateCitationsTests(unittest.TestCase):
    def test_valid_citation_is_preserved(self) -> None:
        chunk = _make_chunk()
        answer = f"Some claim. [CITE:{chunk.chunk_id}]"

        result = validate_citations(answer, [chunk])

        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.citations[0].chunk_id, chunk.chunk_id)
        self.assertEqual(result.rejected_citation_count, 0)

    def test_citation_metadata_matches_source_chunk(self) -> None:
        chunk = _make_chunk(
            page_number=42, section_identifier="4.3.2", retrieval_score=0.87, retrieval_method="vector"
        )
        answer = f"A claim. [CITE:{chunk.chunk_id}]"

        result = validate_citations(answer, [chunk])
        citation = result.citations[0]

        self.assertEqual(citation.page_number, 42)
        self.assertEqual(citation.section_identifier, "4.3.2")
        self.assertEqual(citation.confidence_score, 0.87)
        self.assertEqual(citation.retrieval_method, "vector")
        self.assertEqual(citation.excerpt, chunk.chunk_text)

    def test_hallucinated_chunk_id_is_rejected(self) -> None:
        known_chunk = _make_chunk()
        fake_id = uuid.uuid4()
        answer = f"A claim. [CITE:{fake_id}]"

        result = validate_citations(answer, [known_chunk])

        self.assertEqual(result.citations, [])
        self.assertEqual(result.rejected_citation_count, 1)

    def test_malformed_uuid_is_rejected_not_raised(self) -> None:
        known_chunk = _make_chunk()
        # 36 hex-valid characters (matches the marker regex) but no hyphen
        # structure — well-formed enough to match, malformed as a UUID.
        malformed = "a" * 36
        answer = f"A claim. [CITE:{malformed}]"

        result = validate_citations(answer, [known_chunk])

        self.assertEqual(result.citations, [])
        self.assertEqual(result.rejected_citation_count, 1)

    def test_mixed_valid_and_invalid_citations(self) -> None:
        valid_chunk = _make_chunk()
        fake_id = uuid.uuid4()
        answer = f"First claim. [CITE:{valid_chunk.chunk_id}] Second claim. [CITE:{fake_id}]"

        result = validate_citations(answer, [valid_chunk])

        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.citations[0].chunk_id, valid_chunk.chunk_id)
        self.assertEqual(result.rejected_citation_count, 1)

    def test_duplicate_valid_citation_is_deduplicated_not_rejected(self) -> None:
        chunk = _make_chunk()
        answer = f"Claim one. [CITE:{chunk.chunk_id}] Claim two, same source. [CITE:{chunk.chunk_id}]"

        result = validate_citations(answer, [chunk])

        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.rejected_citation_count, 0)

    def test_no_citation_markers_returns_empty(self) -> None:
        chunk = _make_chunk()
        answer = "An answer with no citation markers at all."

        result = validate_citations(answer, [chunk])

        self.assertEqual(result.citations, [])
        self.assertEqual(result.rejected_citation_count, 0)

    def test_empty_retrieved_chunks_rejects_any_marker(self) -> None:
        fake_id = uuid.uuid4()
        answer = f"A claim. [CITE:{fake_id}]"

        result = validate_citations(answer, [])

        self.assertEqual(result.citations, [])
        self.assertEqual(result.rejected_citation_count, 1)
    
    def test_citation_marker_with_space_after_colon_is_accepted(self) -> None:
        # Exactly the suspected failure mode: the model copying the
        # context block's [CHUNK_ID: <uuid>] spacing instead of the
        # instructed no-space [CITE:<uuid>] format.
        chunk = _make_chunk()
        answer = f"A claim. [CITE: {chunk.chunk_id}]"

        result = validate_citations(answer, [chunk])

        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.rejected_citation_count, 0)