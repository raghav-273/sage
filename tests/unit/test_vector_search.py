# tests/unit/test_vector_search.py
"""
Unit tests for services.retrieval.vector_search.

Embeddings are hand-constructed 384-dimensional one-hot-style vectors
(not real model output) so cosine similarity ranking is mathematically
predictable without loading any ML model — keeps these tests fast and
fully deterministic.
"""

from __future__ import annotations

from django.test import TestCase

from apps.chunks.models import ContentChunk
from apps.documents.models import Document, DocumentPage
from services.retrieval.vector_search import VectorSearchError, vector_search

DIM = 384


def _one_hot(index: int) -> list[float]:
    vec = [0.0] * DIM
    vec[index] = 1.0
    return vec


def _near(index: int, noise_index: int, noise: float = 0.1) -> list[float]:
    vec = _one_hot(index)
    vec[noise_index] = noise
    return vec


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


def _make_chunk(
    document: Document,
    page: DocumentPage,
    chunk_index: int,
    embedding: list[float] | None,
    section_identifier: str | None = None,
) -> ContentChunk:
    return ContentChunk.objects.create(
        document=document,
        page=page,
        chunk_index=chunk_index,
        chunk_text=f"chunk {chunk_index} text",
        section_identifier=section_identifier,
        embedding=embedding,
    )


class VectorSearchTests(TestCase):
    def setUp(self) -> None:
        self.ready_doc = _make_document(Document.Status.READY)
        self.ready_page = _make_page(self.ready_doc)

        self.chunk_a = _make_chunk(
            self.ready_doc, self.ready_page, 0, _one_hot(0), section_identifier="4.1"
        )
        self.chunk_b = _make_chunk(
            self.ready_doc, self.ready_page, 1, _one_hot(1), section_identifier="4.2"
        )

    def test_returns_results_ordered_by_similarity(self) -> None:
        query = _near(0, 1, noise=0.1)  # closer to chunk_a than chunk_b
        results = vector_search(query, top_k=10)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].chunk_id, self.chunk_a.id)
        self.assertEqual(results[1].chunk_id, self.chunk_b.id)
        self.assertGreater(results[0].score, results[1].score)

    def test_respects_top_k(self) -> None:
        results = vector_search(_one_hot(0), top_k=1)
        self.assertEqual(len(results), 1)

    def test_excludes_null_embeddings(self) -> None:
        null_chunk = _make_chunk(self.ready_doc, self.ready_page, 2, embedding=None)
        results = vector_search(_one_hot(0), top_k=10)
        chunk_ids = {r.chunk_id for r in results}
        self.assertEqual(len(results), 2)
        self.assertNotIn(null_chunk.id, chunk_ids)

    def test_excludes_non_ready_documents(self) -> None:
        pending_doc = _make_document(Document.Status.PENDING)
        pending_page = _make_page(pending_doc)
        pending_chunk = _make_chunk(pending_doc, pending_page, 0, _one_hot(0))

        results = vector_search(_one_hot(0), top_k=10)
        chunk_ids = {r.chunk_id for r in results}
        self.assertNotIn(pending_chunk.id, chunk_ids)

    def test_filters_by_document_ids(self) -> None:
        other_doc = _make_document(Document.Status.READY)
        other_page = _make_page(other_doc)
        other_chunk = _make_chunk(other_doc, other_page, 0, _one_hot(0))

        results = vector_search(_one_hot(0), top_k=10, document_ids=[self.ready_doc.id])
        chunk_ids = {r.chunk_id for r in results}
        self.assertNotIn(other_chunk.id, chunk_ids)
        self.assertIn(self.chunk_a.id, chunk_ids)

    def test_raises_on_dimension_mismatch(self) -> None:
        with self.assertRaises(VectorSearchError):
            vector_search([0.0, 1.0, 2.0], top_k=5)

    def test_result_metadata_matches_source_chunk(self) -> None:
        result = vector_search(_one_hot(0), top_k=1)[0]
        self.assertEqual(result.document_id, self.ready_doc.id)
        self.assertEqual(result.page_number, self.ready_page.page_number)
        self.assertEqual(result.section_identifier, "4.1")