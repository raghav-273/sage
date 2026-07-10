# tests/integration/test_portal_outline.py
"""Integration tests for the Clause Navigator view."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.chunks.models import ContentChunk
from apps.documents.models import Document, DocumentPage


class DocumentOutlinePageTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.document = Document.objects.create(
            name="RDSO Spec", original_filename="rdso.pdf",
            file_path="documents/rdso.pdf", file_size_bytes=1,
            status=Document.Status.READY,
        )
        self.page = DocumentPage.objects.create(
            document=self.document, page_number=1, raw_text="text",
        )
        ContentChunk.objects.create(
            document=self.document, page=self.page, chunk_index=0,
            chunk_text="Track gauge requirements...", chunk_type="text",
            section_identifier="4",
        )
        ContentChunk.objects.create(
            document=self.document, page=self.page, chunk_index=1,
            chunk_text="Minimum gauge specification...", chunk_type="text",
            section_identifier="4.3",
        )
        ContentChunk.objects.create(
            document=self.document, page=self.page, chunk_index=2,
            chunk_text="Rail joint tensile strength shall not be less than 720 MPa.",
            chunk_type="text", section_identifier="Clause 4.3.2",
        )

    def test_page_loads_with_clause_hierarchy(self) -> None:
        response = self.client.get(reverse("document-outline-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "4.3.2")
        self.assertContains(response, "Clause Navigator")

    def test_clause_prefix_normalised_in_outline(self) -> None:
        response = self.client.get(reverse("document-outline-page", args=[self.document.id]))
        # "Clause 4.3.2" should appear as "4.3.2" after normalisation
        self.assertContains(response, "4.3.2")

    def test_no_clauses_shows_empty_state(self) -> None:
        empty_doc = Document.objects.create(
            name="No Clauses", original_filename="nc.pdf",
            file_path="documents/nc.pdf", file_size_bytes=1,
            status=Document.Status.READY,
        )
        response = self.client.get(reverse("document-outline-page", args=[empty_doc.id]))
        self.assertContains(response, "No structured clause identifiers found")

    def test_stat_counts_are_correct(self) -> None:
        response = self.client.get(reverse("document-outline-page", args=[self.document.id]))
        outline = response.context["outline"]
        # 3 chunks → 3 distinct clause identifiers after normalisation
        self.assertEqual(outline.total_clauses, 3)

    def test_anonymous_access_redirects_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("document-outline-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 302)

    def test_nonexistent_document_returns_404(self) -> None:
        response = self.client.get(reverse("document-outline-page", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)