# tests/unit/test_keyword_search.py
"""Unit tests for services.retrieval.keyword_search."""

from __future__ import annotations

from django.test import TestCase

from apps.chunks.models import ContentChunk
from apps.documents.models import Document, DocumentPage
from services.retrieval.keyword_search import KeywordSearchError, keyword_search


def _make_document(status: str) -> Document:
    return Document.objects.create(
        name="test-doc",
        original_filename="test.pdf",
        file_path="documents/test.pdf",
        file_size_bytes=100,
        status=status,
    )


def _make_page(document: Document, page_number: int = 1) -> DocumentPage:
    return DocumentPage.objects.create(document=document, page_number=page_number, raw_text="text")


def _make_chunk(document: Document, page: DocumentPage, chunk_index: int, chunk_text: str) -> ContentChunk:
    return ContentChunk.objects.create(
        document=document, page=page, chunk_index=chunk_index, chunk_text=chunk_text
    )


class KeywordSearchTests(TestCase):
    def setUp(self) -> None:
        self.ready_doc = _make_document(Document.Status.READY)
        self.ready_page = _make_page(self.ready_doc)

        self.tensile_chunk = _make_chunk(
            self.ready_doc, self.ready_page, 0,
            "The minimum tensile strength of fish plate joints shall not be less than 720 MPa.",
        )
        self.unrelated_chunk = _make_chunk(
            self.ready_doc, self.ready_page, 1,
            "Ballast cleaning machines shall be inspected annually for wear.",
        )

    def test_finds_matching_terms(self) -> None:
        results = keyword_search("tensile strength", top_k=10)
        chunk_ids = {r.chunk_id for r in results}
        self.assertIn(self.tensile_chunk.id, chunk_ids)
        self.assertNotIn(self.unrelated_chunk.id, chunk_ids)

    def test_no_match_returns_empty(self) -> None:
        results = keyword_search("xenotransplantation", top_k=10)
        self.assertEqual(results, [])

    def test_raises_on_empty_query(self) -> None:
        with self.assertRaises(KeywordSearchError):
            keyword_search("   ", top_k=10)

    def test_excludes_non_ready_documents(self) -> None:
        pending_doc = _make_document(Document.Status.PENDING)
        pending_page = _make_page(pending_doc)
        pending_chunk = _make_chunk(pending_doc, pending_page, 0, "tensile strength requirements")

        results = keyword_search("tensile strength", top_k=10)
        chunk_ids = {r.chunk_id for r in results}
        self.assertNotIn(pending_chunk.id, chunk_ids)

    def test_filters_by_document_ids(self) -> None:
        other_doc = _make_document(Document.Status.READY)
        other_page = _make_page(other_doc)
        other_chunk = _make_chunk(other_doc, other_page, 0, "tensile strength alternative source")

        results = keyword_search("tensile strength", top_k=10, document_ids=[self.ready_doc.id])
        chunk_ids = {r.chunk_id for r in results}
        self.assertNotIn(other_chunk.id, chunk_ids)
        self.assertIn(self.tensile_chunk.id, chunk_ids)

    def test_results_ordered_by_rank_descending(self) -> None:
        strong_match = _make_chunk(
            self.ready_doc, self.ready_page, 2,
            "tensile strength tensile strength tensile strength",
        )
        results = keyword_search("tensile strength", top_k=10)
        self.assertEqual(results[0].chunk_id, strong_match.id)