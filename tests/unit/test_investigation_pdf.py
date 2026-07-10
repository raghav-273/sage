# tests/unit/test_investigation_pdf.py
"""Unit tests for investigation PDF generation."""

from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase

from services.export.investigation_pdf import generate_investigation_pdf


def _make_mock_session(title: str = "Track Gauge Review", turn_count: int = 2):
    session = mock.MagicMock()
    session.title = title
    session.document.name = "RDSO_Spec_2024.pdf"
    session.user.username = "engineer"
    session.created_at.strftime.return_value = "2026-07-06 10:00"

    turns = []
    for i in range(turn_count):
        turn = mock.MagicMock()
        turn.turn_index = i
        turn.query_text = f"Question {i + 1}: What is the requirement for section {i + 1}?"
        turn.answer_text = f"The requirement is X. [1]"
        turn.has_valid_citations = True
        turn.retrieved_chunk_count = 1
        turn.citations = [
            {
                "chunk_id": str(uuid.uuid4()),
                "document_id": str(uuid.uuid4()),
                "page_number": 42 + i,
                "section_identifier": f"4.{i + 1}",
                "excerpt": "The minimum tensile strength shall not be less than 720 MPa.",
                "confidence_score": 0.91,
                "retrieval_method": "hybrid",
                "image_path": None,
            }
        ]
        turns.append(turn)

    session.turns.order_by.return_value = turns
    return session


class GenerateInvestigationPdfTests(TestCase):
    def test_returns_bytes(self) -> None:
        session = _make_mock_session()
        result = generate_investigation_pdf(session)
        self.assertIsInstance(result, bytes)

    def test_output_is_valid_pdf(self) -> None:
        session = _make_mock_session()
        result = generate_investigation_pdf(session)
        self.assertTrue(result.startswith(b"%PDF"), "PDF must start with %PDF header")

    def test_empty_session_produces_pdf(self) -> None:
        session = _make_mock_session(turn_count=0)
        result = generate_investigation_pdf(session)
        self.assertTrue(result.startswith(b"%PDF"))
        self.assertGreater(len(result), 1024)

    def test_untitled_session_uses_fallback(self) -> None:
        session = _make_mock_session(title="")
        result = generate_investigation_pdf(session)
        self.assertTrue(result.startswith(b"%PDF"))

    def test_pdf_is_non_empty_for_multi_turn_session(self) -> None:
        session = _make_mock_session(turn_count=5)
        result = generate_investigation_pdf(session)
        single = generate_investigation_pdf(_make_mock_session(turn_count=1))
        self.assertGreater(len(result), len(single), "5-finding report should be larger than 1-finding")