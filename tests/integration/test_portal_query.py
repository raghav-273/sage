# tests/integration/test_portal_query.py
"""
Integration tests for the query page and its HTMX submission endpoint.

generate_answer is mocked — its own logic is already covered by
tests/unit/test_generation_service.py; these verify the HTML form
contract, citation rendering, and the portal-side rate limiter.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.documents.models import Document
from services.generation.citation_validator import Citation
from services.generation.generation_service import AnswerResult


def _make_result(with_citation: bool) -> AnswerResult:
    citations = []
    if with_citation:
        citations = [
            Citation(
                chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), page_number=4,
                section_identifier="4.1", excerpt="The minimum tensile strength is 720 MPa.",
                confidence_score=0.91, retrieval_method="hybrid",
            )
        ]
    answer_text = f"720 MPa is required. [CITE:{citations[0].chunk_id}]" if with_citation else ""
    return AnswerResult(
        query="test query", answer_text=answer_text, citations=citations,
        has_valid_citations=with_citation,
        retrieved_chunk_count=1 if with_citation else 0, rejected_citation_count=0,
    )


class QueryPageTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")

    def test_get_shows_only_ready_documents(self) -> None:
        Document.objects.create(
            name="Ready Doc", original_filename="r.pdf", file_path="documents/r.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        Document.objects.create(
            name="Pending Doc", original_filename="p.pdf", file_path="documents/p.pdf",
            file_size_bytes=1, status=Document.Status.PENDING,
        )
        response = self.client.get(reverse("query-page"))
        self.assertContains(response, "Ready Doc")
        self.assertNotContains(response, "Pending Doc")

    def test_anonymous_access_redirects_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("query-page"))
        self.assertEqual(response.status_code, 302)


class QuerySubmitTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")

    @mock.patch("apps.portal.views.generate_answer")
    def test_cited_answer_renders_numbered_citation(self, mock_generate) -> None:
        mock_generate.return_value = _make_result(with_citation=True)

        response = self.client.post(reverse("query-submit"), {"query": "tensile strength?"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "[1]")
        self.assertContains(response, "720 MPa")
        self.assertNotContains(response, "[CITE:")

    @mock.patch("apps.portal.views.generate_answer")
    def test_refusal_shows_unsupported_message(self, mock_generate) -> None:
        mock_generate.return_value = _make_result(with_citation=False)

        response = self.client.post(reverse("query-submit"), {"query": "unanswerable?"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "do not contain sufficient information")

    def test_empty_query_shows_error_without_calling_generate_answer(self) -> None:
        with mock.patch("apps.portal.views.generate_answer") as mock_generate:
            response = self.client.post(reverse("query-submit"), {"query": "   "})
            mock_generate.assert_not_called()
        self.assertContains(response, "Please enter a question")

    @mock.patch("apps.portal.views.generate_answer")
    def test_document_ids_passed_through(self, mock_generate) -> None:
        mock_generate.return_value = _make_result(with_citation=True)
        doc_id = str(uuid.uuid4())

        self.client.post(reverse("query-submit"), {"query": "a question", "document_ids": [doc_id]})

        call_kwargs = mock_generate.call_args.kwargs
        self.assertEqual([str(d) for d in call_kwargs["document_ids"]], [doc_id])

    @mock.patch("apps.portal.views.generate_answer")
    def test_rate_limit_blocks_after_threshold(self, mock_generate) -> None:
        mock_generate.return_value = _make_result(with_citation=True)

        for _ in range(8):  # default PORTAL_QUERY_RATE_LIMIT_MAX_REQUESTS
            self.client.post(reverse("query-submit"), {"query": "a question"})

        response = self.client.post(reverse("query-submit"), {"query": "one more"})
        self.assertContains(response, "Too many questions")