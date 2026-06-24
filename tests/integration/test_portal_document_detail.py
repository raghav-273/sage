
# tests/integration/test_portal_document_detail.py
"""Integration tests for the document detail page and status polling partial."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.documents.models import Document


class DocumentDetailPageTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")

    def test_ready_document_shows_no_polling_attribute(self) -> None:
        document = Document.objects.create(
            name="Ready Doc", original_filename="r.pdf", file_path="documents/r.pdf",
            file_size_bytes=1, status=Document.Status.READY, page_count=10,
        )
        response = self.client.get(reverse("document-detail-page", args=[document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ready Doc")
        self.assertNotContains(response, "hx-trigger")

    def test_in_progress_document_shows_polling_attribute(self) -> None:
        document = Document.objects.create(
            name="Processing Doc", original_filename="p.pdf", file_path="documents/p.pdf",
            file_size_bytes=1, status=Document.Status.EMBEDDING,
        )
        response = self.client.get(reverse("document-detail-page", args=[document.id]))
        self.assertContains(response, "hx-trigger")
        self.assertContains(response, reverse("document-status-partial", args=[document.id]))

    def test_failed_document_shows_error_message_and_no_polling(self) -> None:
        document = Document.objects.create(
            name="Failed Doc", original_filename="f.pdf", file_path="documents/f.pdf",
            file_size_bytes=1, status=Document.Status.FAILED, error_message="PDF could not be parsed.",
        )
        response = self.client.get(reverse("document-detail-page", args=[document.id]))
        self.assertContains(response, "PDF could not be parsed.")
        self.assertNotContains(response, "hx-trigger")

    def test_nonexistent_document_returns_404(self) -> None:
        response = self.client.get(reverse("document-detail-page", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_access_redirects_to_login(self) -> None:
        document = Document.objects.create(
            name="Doc", original_filename="d.pdf", file_path="documents/d.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        self.client.logout()
        response = self.client.get(reverse("document-detail-page", args=[document.id]))
        self.assertEqual(response.status_code, 302)


class DocumentStatusPartialTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")

    def test_partial_returns_only_fragment(self) -> None:
        document = Document.objects.create(
            name="Doc", original_filename="d.pdf", file_path="documents/d.pdf",
            file_size_bytes=1, status=Document.Status.CHUNKING,
        )
        response = self.client.get(reverse("document-status-partial", args=[document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, "CHUNKING")

    def test_partial_stops_self_perpetuating_once_terminal(self) -> None:
        document = Document.objects.create(
            name="Doc", original_filename="d.pdf", file_path="documents/d.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        response = self.client.get(reverse("document-status-partial", args=[document.id]))
        self.assertNotContains(response, "hx-trigger")