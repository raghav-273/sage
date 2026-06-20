# tests/integration/test_ingestion_pipeline.py
"""
Integration test for apps.ingestion.pipeline.run_ingestion_pipeline.

Covers the exact gap from the investigation: Document.status never
transitioned PENDING -> READY because no orchestration step set it.
Uses the real local embedding model (free, local, no network dependency)
rather than a fake client — this is an end-to-end check of the actual
production path, not a unit test of an isolated function.
"""

from __future__ import annotations

from pathlib import Path

import fitz
from django.conf import settings
from django.test import TestCase

from apps.chunks.models import ContentChunk
from apps.documents.models import Document, DocumentPage
from apps.ingestion.pipeline import IngestionPipelineError, run_ingestion_pipeline


def _create_test_pdf(path: Path) -> None:
    """Generates a minimal one-page PDF using PyMuPDF — no fixture file needed."""
    pdf_doc = fitz.open()
    page = pdf_doc.new_page()
    page.insert_text(
        (72, 72),
        "Section 4.1: The minimum tensile strength for rail joints is 720 MPa.",
    )
    pdf_doc.save(str(path))
    pdf_doc.close()


class IngestionPipelineTests(TestCase):
    def setUp(self) -> None:
        relative_path = Path("documents") / "integration_test.pdf"
        absolute_path = Path(settings.MEDIA_ROOT) / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        _create_test_pdf(absolute_path)

        self.document = Document.objects.create(
            name="integration-test-doc",
            original_filename="integration_test.pdf",
            file_path=str(relative_path),
            file_size_bytes=absolute_path.stat().st_size,
        )

    def test_pending_transitions_to_ready(self) -> None:
        self.assertEqual(self.document.status, Document.Status.PENDING)

        run_ingestion_pipeline(self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.READY)
        self.assertIsNone(self.document.error_message)

    def test_pages_and_chunks_are_created(self) -> None:
        run_ingestion_pipeline(self.document.id)

        self.assertTrue(DocumentPage.objects.filter(document=self.document).exists())
        self.assertTrue(ContentChunk.objects.filter(document=self.document).exists())

    def test_chunks_have_embeddings_after_pipeline(self) -> None:
        # The specific gap a status-only fix would have missed: READY with
        # NULL embeddings would still be invisible to vector_search.
        run_ingestion_pipeline(self.document.id)

        chunks = ContentChunk.objects.filter(document=self.document)
        self.assertGreater(chunks.count(), 0)
        for chunk in chunks:
            self.assertIsNotNone(chunk.embedding)

    def test_failure_sets_status_failed_with_error_message(self) -> None:
        # Force a failure inside extract_document() by pointing file_path
        # at a non-existent file, without touching any extraction code.
        self.document.file_path = "documents/this-file-does-not-exist.pdf"
        self.document.save(update_fields=["file_path"])

        with self.assertRaises(IngestionPipelineError):
            run_ingestion_pipeline(self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.FAILED)
        self.assertIsNotNone(self.document.error_message)

    def test_ready_document_is_visible_to_vector_search(self) -> None:
        # Closes the loop: confirms the actual reported blocker (vector
        # search excluding the document) is genuinely resolved — not just
        # that the status field looks correct.
        from services.retrieval.vector_search import vector_search

        run_ingestion_pipeline(self.document.id)

        chunk = ContentChunk.objects.filter(document=self.document).first()
        results = vector_search(chunk.embedding, top_k=5, document_ids=[self.document.id])

        self.assertTrue(any(r.chunk_id == chunk.id for r in results))