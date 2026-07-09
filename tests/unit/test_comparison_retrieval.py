# tests/unit/test_comparison_retrieval.py
"""
Unit tests for cross-document comparison generation logic.
No real retrieval — pure section parsing and result structure.
"""

from __future__ import annotations

import unittest

from services.generation.generation_service import (
    ComparisonResult,
    _parse_comparison_sections,
)
import uuid


class ParseComparisonSectionsTests(unittest.TestCase):
    def test_all_four_sections_parsed(self) -> None:
        text = (
            "## Agreements\nBoth require 720 MPa.\n\n"
            "## Conflicts\nDoc A says 1435 mm; Doc B says 1676 mm.\n\n"
            "## Only in Document A\nSee Clause 4.3.\n\n"
            "## Only in Document B\nNone identified in the retrieved clauses."
        )
        sections = _parse_comparison_sections(text)
        self.assertIn("Agreements", sections)
        self.assertIn("Conflicts", sections)
        self.assertIn("Only in Document A", sections)
        self.assertIn("Only in Document B", sections)

    def test_section_content_stripped(self) -> None:
        text = "## Agreements\n\n  Both require 720 MPa.  \n\n## Conflicts\nNone."
        sections = _parse_comparison_sections(text)
        self.assertEqual(sections["Agreements"], "Both require 720 MPa.")

    def test_no_headers_returns_analysis_key(self) -> None:
        text = "There are no headers here. Just a plain analysis."
        sections = _parse_comparison_sections(text)
        self.assertIn("Analysis", sections)
        self.assertEqual(sections["Analysis"], text)

    def test_preamble_before_first_header_captured(self) -> None:
        text = "Introduction text.\n\n## Agreements\nBoth require 720 MPa."
        sections = _parse_comparison_sections(text)
        self.assertIn("Preamble", sections)
        self.assertEqual(sections["Preamble"], "Introduction text.")

    def test_empty_section_body_preserved(self) -> None:
        text = "## Agreements\n## Conflicts\nSome conflict."
        sections = _parse_comparison_sections(text)
        self.assertEqual(sections["Agreements"], "")
        self.assertEqual(sections["Conflicts"], "Some conflict.")

    def test_comparison_result_sections_property(self) -> None:
        result = ComparisonResult(
            query="q",
            document_a_id=uuid.uuid4(),
            document_b_id=uuid.uuid4(),
            document_a_name="Doc A",
            document_b_name="Doc B",
            answer_text="## Agreements\nSame value. [1]",
            rendered_answer="## Agreements\nSame value. [1]",
            citations=[],
            has_valid_citations=False,
            retrieved_count_a=1,
            retrieved_count_b=1,
            rejected_citation_count=0,
        )
        sections = result.sections
        self.assertIn("Agreements", sections)