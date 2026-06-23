# tests/integration/test_portal_upload.py
"""
Integration tests for the portal upload and detail-placeholder pages.
Mocks the Celery task — actual ingestion is already covered by
test_ingestion_task.py; these verify the HTML form contract and that
validation is genuinely shared with the API, not reimplemented.
"""

from __future__ import annotations

import io
import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.documents.models import Document


def _make_minimal_pdf_bytes() -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Test content.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class DocumentUploadPageTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")

    def test_get_shows_upload_form(self) -> None:
        response = self.client.get(reverse("document-upload-page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a document")

    @mock.patch("apps.documents.services.run_ingestion_pipeline_task")
    def test_valid_upload_creates_document_and_redirects(self, mock_task) -> None:
        upload_file = io.BytesIO(_make_minimal_pdf_bytes())
        upload_file.name = "test.pdf"

        response = self.client.post(
            reverse("document-upload-page"), {"file": upload_file, "name": "My Document"},
        )

        document = Document.objects.get(name="My Document")
        self.assertRedirects(response, reverse("document-detail-page", args=[document.id]))
        self.assertEqual(document.status, Document.Status.QUEUED)
        mock_task.delay.assert_called_once_with(str(document.id))

    def test_invalid_file_type_rerenders_with_error(self) -> None:
        upload_file = io.BytesIO(b"not a pdf")
        upload_file.name = "test.txt"

        response = self.client.post(reverse("document-upload-page"), {"file": upload_file})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only PDF files are accepted")
        self.assertEqual(Document.objects.count(), 0)

    def test_missing_file_rerenders_with_error(self) -> None:
        response = self.client.post(reverse("document-upload-page"), {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Document.objects.count(), 0)

    def test_anonymous_access_redirects_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("document-upload-page"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class DocumentDetailPageTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.document = Document.objects.create(
            name="Existing Doc", original_filename="e.pdf", file_path="documents/e.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )

    def test_detail_page_shows_document(self) -> None:
        response = self.client.get(reverse("document-detail-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Existing Doc")

    def test_nonexistent_document_returns_404(self) -> None:
        response = self.client.get(reverse("document-detail-page", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)