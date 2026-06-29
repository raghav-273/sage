# tests/unit/test_answer_rendering.py
"""Unit tests for apps.portal.answer_rendering. Pure logic — no database needed."""

from __future__ import annotations

import unittest
import uuid

from services.generation.answer_rendering import render_answer_with_numbered_citations
from services.generation.citation_validator import Citation
from services.generation.generation_service import AnswerResult


def _make_citation(chunk_id: uuid.UUID) -> Citation:
    return Citation(
        chunk_id=chunk_id, document_id=uuid.uuid4(), page_number=1,
        section_identifier="4.1", excerpt="excerpt text",
        confidence_score=0.9, retrieval_method="hybrid",
    )


class RenderAnswerWithNumberedCitationsTests(unittest.TestCase):
    def test_single_marker_replaced_with_number_one(self) -> None:
        chunk_id = uuid.uuid4()
        result = AnswerResult(
            query="q", answer_text=f"A claim. [CITE:{chunk_id}]",
            citations=[_make_citation(chunk_id)], has_valid_citations=True,
            retrieved_chunk_count=1, rejected_citation_count=0,
        )
        self.assertEqual(render_answer_with_numbered_citations(result), "A claim. [1]")

    def test_multiple_markers_numbered_in_citation_order(self) -> None:
        id_a, id_b = uuid.uuid4(), uuid.uuid4()
        result = AnswerResult(
            query="q", answer_text=f"First. [CITE:{id_a}] Second. [CITE:{id_b}]",
            citations=[_make_citation(id_a), _make_citation(id_b)], has_valid_citations=True,
            retrieved_chunk_count=2, rejected_citation_count=0,
        )
        self.assertEqual(
            render_answer_with_numbered_citations(result), "First. [1] Second. [2]"
        )

    def test_repeated_marker_for_same_chunk_gets_same_number(self) -> None:
        chunk_id = uuid.uuid4()
        result = AnswerResult(
            query="q", answer_text=f"One. [CITE:{chunk_id}] Two, same source. [CITE:{chunk_id}]",
            citations=[_make_citation(chunk_id)], has_valid_citations=True,
            retrieved_chunk_count=1, rejected_citation_count=0,
        )
        self.assertEqual(
            render_answer_with_numbered_citations(result),
            "One. [1] Two, same source. [1]",
        )

    def test_marker_with_no_matching_citation_is_stripped(self) -> None:
        known_id, unknown_id = uuid.uuid4(), uuid.uuid4()
        result = AnswerResult(
            query="q", answer_text=f"Known. [CITE:{known_id}] Unknown. [CITE:{unknown_id}]",
            citations=[_make_citation(known_id)], has_valid_citations=True,
            retrieved_chunk_count=1, rejected_citation_count=0,
        )
        self.assertEqual(
            render_answer_with_numbered_citations(result), "Known. [1] Unknown. "
        )

    def test_no_markers_returns_text_unchanged(self) -> None:
        result = AnswerResult(
            query="q", answer_text="No citations here.",
            citations=[], has_valid_citations=False,
            retrieved_chunk_count=0, rejected_citation_count=0,
        )
        self.assertEqual(render_answer_with_numbered_citations(result), "No citations here.")