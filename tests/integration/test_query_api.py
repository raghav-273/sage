# tests/integration/test_query_api.py
"""
Integration tests for the query endpoint.

generate_answer() itself is already covered by
tests/unit/test_generation_service.py — these tests verify the HTTP
contract (request validation, response serialization, status codes), so
generate_answer is mocked here rather than re-exercising the full
retrieval+generation pipeline.
"""

from __future__ import annotations

import uuid
from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase

from services.generation.citation_validator import Citation
from services.generation.generation_service import AnswerResult


def _make_fake_result(with_citation: bool = True) -> AnswerResult:
    citations = []
    if with_citation:
        citations = [
            Citation(
                chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), page_number=4,
                section_identifier="4.1", excerpt="sample excerpt",
                confidence_score=0.9, retrieval_method="hybrid",
            )
        ]
    return AnswerResult(
        query="test query",
        answer_text="A cited answer." if with_citation else "",
        citations=citations,
        has_valid_citations=with_citation,
        retrieved_chunk_count=1 if with_citation else 0,
        rejected_citation_count=0,
    )


class QueryAPITests(APITestCase):
    @mock.patch("apps.api.views.generate_answer")
    def test_query_returns_cited_answer(self, mock_generate_answer) -> None:
        mock_generate_answer.return_value = _make_fake_result(with_citation=True)

        response = self.client.post(
            "/api/query/", {"query": "what is the tensile strength?"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["has_valid_citations"])
        self.assertEqual(len(response.data["citations"]), 1)
        self.assertEqual(response.data["retrieved_chunk_count"], 1)

    @mock.patch("apps.api.views.generate_answer")
    def test_query_returns_refusal_without_citations(self, mock_generate_answer) -> None:
        mock_generate_answer.return_value = _make_fake_result(with_citation=False)

        response = self.client.post("/api/query/", {"query": "unanswerable question"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["has_valid_citations"])
        self.assertEqual(response.data["citations"], [])

    def test_query_rejects_empty_query(self) -> None:
        response = self.client.post("/api/query/", {"query": "   "}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_query_rejects_missing_query_field(self) -> None:
        response = self.client.post("/api/query/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch("apps.api.views.generate_answer")
    def test_query_passes_document_ids_through(self, mock_generate_answer) -> None:
        mock_generate_answer.return_value = _make_fake_result(with_citation=True)
        doc_id = str(uuid.uuid4())

        self.client.post("/api/query/", {"query": "a question", "document_ids": [doc_id]}, format="json")

        call_kwargs = mock_generate_answer.call_args.kwargs
        self.assertEqual([str(d) for d in call_kwargs["document_ids"]], [doc_id])

    @mock.patch("apps.api.views.generate_answer")
    def test_generation_error_returns_503(self, mock_generate_answer) -> None:
        from services.llm_client.generation_base import GenerationError
        mock_generate_answer.side_effect = GenerationError("Gemini unavailable")

        response = self.client.post("/api/query/", {"query": "a question"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)