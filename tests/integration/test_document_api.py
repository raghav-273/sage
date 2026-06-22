# tests/integration/test_document_api.py
"""
Integration tests for document upload and detail endpoints.
# OLD LOGIC:
Uses APITestCase (wraps TestCase) — the upload view's ingestion call is
synchronous and single-threaded, no cross-connection threading concern
here unlike the retrieval/generation service tests.

# NEW LOGIC:

Integration tests for document upload and detail endpoints.

The upload test now mocks run_ingestion_pipeline_task rather than letting
it run for real — the endpoint's whole job, post-Celery, is to enqueue
and return immediately; actually exercising the pipeline is covered by
test_ingestion_task.py and the pre-existing test_ingestion_pipeline.py.
"""

from __future__ import annotations

import io
import uuid
from unittest import mock

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.documents.models import Document


def _make_minimal_pdf_bytes() -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Test content for API upload.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class DocumentUploadAPITests(APITestCase):
    
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="tester", password="pass")
        self.client.force_authenticate(user=self.user)
    
    @mock.patch("apps.documents.views.run_ingestion_pipeline_task")
    def test_upload_returns_immediately_with_queued_status(self, mock_task) -> None:
        upload_file = io.BytesIO(_make_minimal_pdf_bytes())
        upload_file.name = "test.pdf"

        response = self.client.post(
            "/api/documents/", {"file": upload_file, "name": "Test Document"}, format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("document_id", response.data)
        self.assertEqual(response.data["status"], Document.Status.QUEUED)

        document = Document.objects.get(id=response.data["document_id"])
        self.assertEqual(document.status, Document.Status.QUEUED)
        mock_task.delay.assert_called_once_with(str(document.id))

    def test_upload_rejects_non_pdf_file(self) -> None:
        upload_file = io.BytesIO(b"not a pdf")
        upload_file.name = "test.txt"

        response = self.client.post("/api/documents/", {"file": upload_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_without_file_returns_400(self) -> None:
        response = self.client.post("/api/documents/", {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DocumentDetailAPITests(APITestCase):
    def setUp(self) -> None:
        
        self.user = User.objects.create_user(username="tester", password="pass")
        self.client.force_authenticate(user=self.user)
        
        self.document = Document.objects.create(
            name="existing-doc", original_filename="existing.pdf",
            file_path="documents/existing.pdf", file_size_bytes=100,
            status=Document.Status.READY, page_count=5,
        )

    def test_get_document_detail(self) -> None:
        response = self.client.get(f"/api/documents/{self.document.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["document_id"], str(self.document.id))
        self.assertEqual(response.data["status"], "READY")
        self.assertEqual(response.data["page_count"], 5)
        self.assertIn("chunk_count", response.data)

    def test_get_nonexistent_document_returns_404(self) -> None:
        response = self.client.get(f"/api/documents/{uuid.uuid4()}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)