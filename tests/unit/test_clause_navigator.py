# tests/unit/test_clause_navigator.py
"""Unit tests for services.documents.clause_navigator. No database needed."""

from __future__ import annotations

import unittest

from services.documents.clause_navigator import (
    ClauseNode,
    normalize_identifier,
)


class NormalizeIdentifierTests(unittest.TestCase):
    def test_plain_numeric(self) -> None:
        self.assertEqual(normalize_identifier("4.3.2"), "4.3.2")
        self.assertEqual(normalize_identifier("4"), "4")
        self.assertEqual(normalize_identifier("12.3"), "12.3")

    def test_clause_prefix_stripped(self) -> None:
        self.assertEqual(normalize_identifier("Clause 4.3.2"), "4.3.2")
        self.assertEqual(normalize_identifier("clause 7.1"), "7.1")

    def test_section_prefix_stripped(self) -> None:
        self.assertEqual(normalize_identifier("Section 3.4"), "3.4")
        self.assertEqual(normalize_identifier("SECTION 7"), "7")

    def test_abbreviation_prefix_stripped(self) -> None:
        self.assertEqual(normalize_identifier("Cl. 4.3"), "4.3")
        self.assertEqual(normalize_identifier("Sec. 7.1"), "7.1")

    def test_leading_trailing_whitespace_handled(self) -> None:
        self.assertEqual(normalize_identifier("  4.3.2  "), "4.3.2")

    def test_non_numeric_returns_none(self) -> None:
        self.assertIsNone(normalize_identifier("Appendix A"))
        self.assertIsNone(normalize_identifier("4.3.2(a)"))
        self.assertIsNone(normalize_identifier("random text"))
        self.assertIsNone(normalize_identifier(""))

    def test_mixed_content_returns_none(self) -> None:
        self.assertIsNone(normalize_identifier("4.3a.2"))


class ClauseNodeCssIdTests(unittest.TestCase):
    def test_css_id_replaces_dots(self) -> None:
        node = ClauseNode(identifier="4.3.2", depth=2)
        self.assertEqual(node.css_id, "clause-4-3-2")

    def test_css_id_top_level(self) -> None:
        node = ClauseNode(identifier="4", depth=0)
        self.assertEqual(node.css_id, "clause-4")