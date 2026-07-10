# tests/integration/test_portal_comparison.py
"""Integration tests for the cross-document comparison views."""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.documents.models import Document
from services.generation.generation_service import ComparisonResult


def _make_doc(name: str) -> Document:
    return Document.objects.create(
        name=name, original_filename=f"{name}.pdf",
        file_path=f"documents/{name}.pdf", file_size_bytes=1,
        status=Document.Status.READY,
    )


def _make_comparison_result(doc_a: Document, doc_b: Document) -> ComparisonResult:
    return ComparisonResult(
        query="tensile strength requirements",
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        document_a_name=doc_a.name,
        document_b_name=doc_b.name,
        answer_text=(
            "## Agreements\nBoth require 720 MPa.\n\n"
            "## Conflicts\nDoc A specifies 23°C; Doc B specifies 25°C.\n\n"
            "## Only in Document A\nClause 4.3.2 applies.\n\n"
            "## Only in Document B\nNone identified in the retrieved clauses."
        ),
        rendered_answer=(
            "## Agreements\nBoth require 720 MPa. [1]\n\n"
            "## Conflicts\nDoc A specifies 23°C [1]; Doc B specifies 25°C [2].\n\n"
            "## Only in Document A\nClause 4.3.2 applies. [1]\n\n"
            "## Only in Document B\nNone identified in the retrieved clauses."
        ),
        citations=[],
        has_valid_citations=False,
        retrieved_count_a=2,
        retrieved_count_b=2,
        rejected_citation_count=0,
    )


class ComparisonPageTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.doc_a = _make_doc("RDSO-T-2024")
        self.doc_b = _make_doc("RDSO-T-2019")

    def test_page_loads_with_two_ready_documents(self) -> None:
        response = self.client.get(reverse("comparison-page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RDSO-T-2024")
        self.assertContains(response, "RDSO-T-2019")

    def test_page_shows_insufficient_docs_message_with_fewer_than_two(self) -> None:
        Document.objects.all().delete()
        _make_doc("Only Doc")
        response = self.client.get(reverse("comparison-page"))
        self.assertContains(response, "At least two READY documents")

    def test_preselect_parameters_populate_dropdowns(self) -> None:
        response = self.client.get(
            reverse("comparison-page"),
            {"document_a": str(self.doc_a.id), "document_b": str(self.doc_b.id)},
        )
        self.assertContains(response, str(self.doc_a.id))
        self.assertContains(response, str(self.doc_b.id))

    def test_anonymous_access_redirects_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("comparison-page"))
        self.assertEqual(response.status_code, 302)


class ComparisonSubmitTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.doc_a = _make_doc("RDSO-T-2024")
        self.doc_b = _make_doc("RDSO-T-2019")

    @mock.patch("apps.portal.views.generate_comparison_answer")
    def test_valid_comparison_renders_sections(self, mock_gen) -> None:
        mock_gen.return_value = _make_comparison_result(self.doc_a, self.doc_b)
        response = self.client.post(reverse("comparison-submit"), {
            "query": "tensile strength requirements",
            "document_a_id": str(self.doc_a.id),
            "document_b_id": str(self.doc_b.id),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agreements")
        self.assertContains(response, "Conflicts")
        self.assertContains(response, "RDSO-T-2024")
        self.assertContains(response, "RDSO-T-2019")

    def test_same_document_rejected(self) -> None:
        with mock.patch("apps.portal.views.generate_comparison_answer") as mock_gen:
            response = self.client.post(reverse("comparison-submit"), {
                "query": "tensile strength",
                "document_a_id": str(self.doc_a.id),
                "document_b_id": str(self.doc_a.id),
            })
            mock_gen.assert_not_called()
        self.assertContains(response, "two different documents")

    def test_empty_query_rejected(self) -> None:
        with mock.patch("apps.portal.views.generate_comparison_answer") as mock_gen:
            response = self.client.post(reverse("comparison-submit"), {
                "query": "   ",
                "document_a_id": str(self.doc_a.id),
                "document_b_id": str(self.doc_b.id),
            })
            mock_gen.assert_not_called()
        self.assertContains(response, "Please enter a comparison query")

    def test_missing_document_rejected(self) -> None:
        response = self.client.post(reverse("comparison-submit"), {
            "query": "tensile strength",
            "document_a_id": str(self.doc_a.id),
            "document_b_id": "",
        })
        self.assertContains(response, "Please select both documents")

    @mock.patch("apps.portal.views.generate_comparison_answer")
    def test_rate_limit_blocks_after_threshold(self, mock_gen) -> None:
        mock_gen.return_value = _make_comparison_result(self.doc_a, self.doc_b)
        for _ in range(8):
            self.client.post(reverse("comparison-submit"), {
                "query": "a query",
                "document_a_id": str(self.doc_a.id),
                "document_b_id": str(self.doc_b.id),
            })
        response = self.client.post(reverse("comparison-submit"), {
            "query": "one more",
            "document_a_id": str(self.doc_a.id),
            "document_b_id": str(self.doc_b.id),
        })
        self.assertContains(response, "Too many requests")

    @mock.patch("apps.portal.views.generate_comparison_answer")
    def test_document_provenance_shown_in_citations(self, mock_gen) -> None:
        from services.generation.citation_validator import Citation
        chunk_id = uuid.uuid4()
        result = _make_comparison_result(self.doc_a, self.doc_b)
        result.citations = [
            Citation(
                chunk_id=chunk_id, document_id=self.doc_a.id, page_number=42,
                section_identifier="4.3.2",
                excerpt="The minimum tensile strength shall be 720 MPa.",
                confidence_score=0.91, retrieval_method="hybrid", image_path=None,
            )
        ]
        result.has_valid_citations = True
        mock_gen.return_value = result

        response = self.client.post(reverse("comparison-submit"), {
            "query": "tensile strength",
            "document_a_id": str(self.doc_a.id),
            "document_b_id": str(self.doc_b.id),
        })
        self.assertContains(response, "comparison-doc-a-badge")