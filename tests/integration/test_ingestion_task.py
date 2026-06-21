# tests/integration/test_ingestion_task.py
"""
Integration test for the Celery task wrapper around run_ingestion_pipeline.

Calls run_ingestion_pipeline_task directly as a plain function, not via
.delay() — @shared_task-decorated functions remain directly callable,
which is the simplest, most robust way to test task logic without a real
broker or worker. It also avoids a known gotcha: override_settings does
NOT retroactively affect an already-configured Celery app instance, since
config_from_object() reads Django settings once at app startup — so
toggling CELERY_TASK_ALWAYS_EAGER via override_settings in a test
silently does nothing.

Testing the real .delay() dispatch through Redis to a live worker is
deliberately out of scope for this automated suite — that's an
infrastructure concern best verified manually (see commands below), not
something that should require a live worker process alongside the test
run.
"""

from __future__ import annotations

from pathlib import Path

import fitz
from django.conf import settings
from django.test import TestCase

from apps.chunks.models import ContentChunk
from apps.documents.models import Document, DocumentPage
from apps.ingestion.pipeline import IngestionPipelineError
from apps.ingestion.tasks import run_ingestion_pipeline_task


def _create_test_pdf(path: Path) -> None:
    pdf_doc = fitz.open()
    page = pdf_doc.new_page()
    page.insert_text((72, 72), "Section 4.1: sample content for the async task test.")
    pdf_doc.save(str(path))
    pdf_doc.close()


class IngestionTaskTests(TestCase):
    def setUp(self) -> None:
        relative_path = Path("documents") / "task_test.pdf"
        absolute_path = Path(settings.MEDIA_ROOT) / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        _create_test_pdf(absolute_path)

        self.document = Document.objects.create(
            name="task-test-doc",
            original_filename="task_test.pdf",
            file_path=str(relative_path),
            file_size_bytes=absolute_path.stat().st_size,
            status=Document.Status.QUEUED,
        )

    def test_task_runs_pipeline_and_reaches_ready(self) -> None:
        run_ingestion_pipeline_task(str(self.document.id))

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.READY)
        self.assertTrue(DocumentPage.objects.filter(document=self.document).exists())

        chunks = ContentChunk.objects.filter(document=self.document)
        self.assertTrue(chunks.exists())
        for chunk in chunks:
            self.assertIsNotNone(chunk.embedding)

    def test_task_accepts_string_document_id(self) -> None:
        # Celery's JSON serializer can't carry a uuid.UUID object — the
        # task must work when called exactly as the view calls it:
        # .delay(str(document.id)).
        run_ingestion_pipeline_task(str(self.document.id))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.READY)

    def test_task_propagates_failure_and_sets_failed_status(self) -> None:
        self.document.file_path = "documents/nonexistent.pdf"
        self.document.save(update_fields=["file_path"])

        with self.assertRaises(IngestionPipelineError):
            run_ingestion_pipeline_task(str(self.document.id))

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.FAILED)
        self.assertIsNotNone(self.document.error_message)