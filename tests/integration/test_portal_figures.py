# tests/integration/test_portal_figures.py
"""Integration tests for the Figure Explorer page."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.chunks.models import DiagramAsset
from apps.documents.models import Document, DocumentPage


class DocumentFiguresPageTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.document = Document.objects.create(
            name="Spec with figures", original_filename="spec.pdf",
            file_path="documents/spec.pdf", file_size_bytes=1,
            status=Document.Status.READY,
        )
        self.page = DocumentPage.objects.create(document=self.document, page_number=1, raw_text="x")
        self.figure_with_caption = DiagramAsset.objects.create(
            document=self.document, page=self.page,
            image_path="images/test/fig1.png", image_format="PNG",
            caption="Cross-section of a rail joint assembly showing bolt positions.",
        )
        self.figure_without_caption = DiagramAsset.objects.create(
            document=self.document, page=self.page,
            image_path="images/test/fig2.png", image_format="PNG",
            caption=None,
        )

    def test_page_loads_and_shows_all_figures(self) -> None:
        response = self.client.get(reverse("document-figures-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cross-section of a rail joint assembly")
        self.assertContains(response, "No caption generated")
        self.assertEqual(response.context["total_figures"], 2)

    def test_caption_search_filters_correctly(self) -> None:
        response = self.client.get(
            reverse("document-figures-page", args=[self.document.id]), {"q": "rail joint"}
        )
        self.assertEqual(response.status_code, 200)
        figures = list(response.context["figures"])
        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0].id, self.figure_with_caption.id)

    def test_search_no_match_shows_empty_state(self) -> None:
        response = self.client.get(
            reverse("document-figures-page", args=[self.document.id]), {"q": "xenotransplantation"}
        )
        self.assertContains(response, "No figures matched")

    def test_nonexistent_document_returns_404(self) -> None:
        response = self.client.get(reverse("document-figures-page", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_access_redirects_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("document-figures-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 302)

    def test_non_ready_document_still_accessible(self) -> None:
        # Figure Explorer should be available regardless of status —
        # engineers may want to review extracted figures even before
        # a document is fully indexed.
        pending_doc = Document.objects.create(
            name="Pending doc", original_filename="p.pdf",
            file_path="documents/p.pdf", file_size_bytes=1,
            status=Document.Status.PENDING,
        )
        response = self.client.get(reverse("document-figures-page", args=[pending_doc.id]))
        self.assertEqual(response.status_code, 200)