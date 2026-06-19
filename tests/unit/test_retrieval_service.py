# tests/unit/test_retrieval_service.py
"""
Unit tests for services.retrieval.retrieval_service.

Uses TransactionTestCase, not TestCase: retrieve() runs vector_search and
keyword_search concurrently in separate threads via ThreadPoolExecutor,
each opening its own database connection. TestCase wraps a test in an
uncommitted transaction on the main thread's connection — data created
there is invisible to a different connection in a different thread.
TransactionTestCase commits data (and truncates tables after each test),
so the worker threads can see it.

A fake EmbeddingClient is injected so these tests never load the real
sentence-transformers model — fast and fully deterministic.
"""

from __future__ import annotations

import uuid

from django.test import TransactionTestCase

from apps.chunks.models import ContentChunk
from apps.documents.models import Document, DocumentPage
from services.llm_client.base import EmbeddingClient
from services.retrieval.retrieval_service import RetrievalError, retrieve

DIM = 384


def _one_hot(index: int) -> list[float]:
    vec = [0.0] * DIM
    vec[index] = 1.0
    return vec


class _FakeEmbeddingClient(EmbeddingClient):
    """Returns a fixed vector for every text, regardless of input."""

    EMBEDDING_DIMENSIONS = DIM

    def __init__(self, fixed_vector: list[float]) -> None:
        self._fixed_vector = fixed_vector

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        return [self._fixed_vector for _ in batch]


def _make_document(status: str = Document.Status.READY) -> Document:
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
    chunk_text: str,
    embedding: list[float] | None,
) -> ContentChunk:
    return ContentChunk.objects.create(
        document=document, page=page, chunk_index=chunk_index,
        chunk_text=chunk_text, embedding=embedding,
    )


class RetrievalServiceTests(TransactionTestCase):
    def setUp(self) -> None:
        self.document = _make_document()
        self.page = _make_page(self.document)

        # Matches both vector (identical embedding) and keyword search.
        self.hybrid_chunk = _make_chunk(
            self.document, self.page, 0,
            "The minimum tensile strength for rail joints is 720 MPa.",
            embedding=_one_hot(0),
        )
        # Matches vector search only — no "tensile"/"strength" in the text.
        self.vector_only_chunk = _make_chunk(
            self.document, self.page, 1,
            "Lorem ipsum unrelated filler content for this fixture.",
            embedding=_one_hot(0),
        )
        # Matches keyword search only — embedding is orthogonal to the query.
        self.keyword_only_chunk = _make_chunk(
            self.document, self.page, 2,
            "Tensile strength tensile strength tensile strength requirements apply here.",
            embedding=_one_hot(200),
        )

    def test_returns_fused_results(self) -> None:
        client = _FakeEmbeddingClient(_one_hot(0))
        results = retrieve("tensile strength", embedding_client=client, top_k=5)
        self.assertGreater(len(results), 0)
        chunk_ids = {r.chunk_id for r in results}
        self.assertIn(self.hybrid_chunk.id, chunk_ids)

    def test_distinguishes_vector_only_keyword_only_and_hybrid(self) -> None:
        # top_k_per_method=2 is essential here: with only 3 chunks total,
        # the default of 10 would return every chunk from vector_search
        # regardless of similarity quality, making everything look
        # "hybrid". Narrowing to 2 forces keyword_only_chunk's near-zero
        # vector score out of the vector results, producing a genuine
        # three-way split.
        client = _FakeEmbeddingClient(_one_hot(0))
        results = retrieve(
            "tensile strength", embedding_client=client, top_k=5, top_k_per_method=2
        )
        by_id = {r.chunk_id: r for r in results}

        self.assertEqual(by_id[self.hybrid_chunk.id].retrieval_method, "hybrid")
        self.assertEqual(by_id[self.vector_only_chunk.id].retrieval_method, "vector")
        self.assertEqual(by_id[self.keyword_only_chunk.id].retrieval_method, "keyword")

    def test_raises_on_empty_query(self) -> None:
        client = _FakeEmbeddingClient(_one_hot(0))
        with self.assertRaises(RetrievalError):
            retrieve("   ", embedding_client=client)

    def test_respects_document_ids_filter(self) -> None:
        other_document = _make_document()
        other_page = _make_page(other_document)
        other_chunk = _make_chunk(
            other_document, other_page, 0, "tensile strength tensile strength", embedding=_one_hot(0)
        )

        client = _FakeEmbeddingClient(_one_hot(0))
        results = retrieve(
            "tensile strength", embedding_client=client,
            document_ids=[self.document.id], top_k=10,
        )
        chunk_ids = {r.chunk_id for r in results}
        self.assertNotIn(other_chunk.id, chunk_ids)

    def test_result_fields_are_populated(self) -> None:
        client = _FakeEmbeddingClient(_one_hot(0))
        result = retrieve("tensile strength", embedding_client=client, top_k=1)[0]
        self.assertIsInstance(result.chunk_id, uuid.UUID)
        self.assertIsInstance(result.chunk_text, str)
        self.assertEqual(result.page_number, self.page.page_number)
        self.assertIn(result.retrieval_method, {"vector", "keyword", "hybrid"})

    def test_default_embedding_client_is_lazily_constructed(self) -> None:
        """
        Confirms retrieve() works without an explicit embedding_client —
        without loading the real model. The lazy factory is monkeypatched
        so SentenceTransformerEmbeddingClient is never instantiated here.
        """
        import services.retrieval.retrieval_service as retrieval_service_module

        original_factory = retrieval_service_module._default_embedding_client
        retrieval_service_module._default_embedding_client = (
            lambda: _FakeEmbeddingClient(_one_hot(0))
        )
        try:
            results = retrieve("tensile strength", top_k=5)
            self.assertGreater(len(results), 0)
        finally:
            retrieval_service_module._default_embedding_client = original_factory