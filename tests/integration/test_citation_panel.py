# tests/integration/test_citation_panel.py
"""Integration tests for the citation context panel endpoint."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.chunks.models import ContentChunk, DiagramAsset
from apps.documents.models import Document, DocumentPage


class ChunkContextPartialTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")

        self.document = Document.objects.create(
            name="RDSO Spec", original_filename="rdso.pdf",
            file_path="documents/rdso.pdf", file_size_bytes=1,
            status=Document.Status.READY,
        )
        self.page = DocumentPage.objects.create(
            document=self.document, page_number=42, raw_text="context text"
        )

        # Create 5 chunks: indices 10–14 so we can verify adjacency precisely
        self.chunks = []
        for i in range(5):
            self.chunks.append(ContentChunk.objects.create(
                document=self.document, page=self.page,
                chunk_index=10 + i,
                chunk_text=f"Chunk {10 + i} content about railway specifications.",
                chunk_type=ContentChunk.ChunkType.TEXT,
            ))

    def test_panel_loads_for_valid_chunk(self) -> None:
        middle_chunk = self.chunks[2]  # index 12, has 2 before and 2 after
        response = self.client.get(
            reverse("chunk-context-partial", args=[middle_chunk.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chunk 12 content")

    def test_panel_shows_adjacent_chunks(self) -> None:
        middle_chunk = self.chunks[2]  # index 12
        response = self.client.get(
            reverse("chunk-context-partial", args=[middle_chunk.id])
        )
        # Should contain the 2 before (10, 11) and 2 after (13, 14)
        self.assertContains(response, "Chunk 10 content")
        self.assertContains(response, "Chunk 11 content")
        self.assertContains(response, "Chunk 13 content")
        self.assertContains(response, "Chunk 14 content")

    def test_panel_marks_cited_chunk_distinctly(self) -> None:
        middle_chunk = self.chunks[2]
        response = self.client.get(
            reverse("chunk-context-partial", args=[middle_chunk.id])
        )
        self.assertContains(response, "cp-chunk-current")
        self.assertContains(response, "Cited passage")

    def test_first_chunk_has_no_before(self) -> None:
        first_chunk = self.chunks[0]  # index 10, nothing before it
        response = self.client.get(
            reverse("chunk-context-partial", args=[first_chunk.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cp-chunk-current")
        # First chunk has 2 after-chunks (indices 11, 12) but zero before-chunks.
        # Both before and after use cp-chunk-adjacent — count is the
        # correct discriminator: 2 (after only), not 0 (which would
        # require no adjacent chunks at all).
        adjacent_count = response.content.count(b"cp-chunk-adjacent")
        self.assertEqual(adjacent_count, 2, "Expected only 2 after-chunks, no before-chunks")

    def test_last_chunk_has_no_after(self) -> None:
        last_chunk = self.chunks[4]  # index 14, nothing after it
        response = self.client.get(
            reverse("chunk-context-partial", args=[last_chunk.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cp-chunk-current")
        # Last chunk has 2 before-chunks (indices 12, 13) but zero after-chunks.
        adjacent_count = response.content.count(b"cp-chunk-adjacent")
        self.assertEqual(adjacent_count, 2, "Expected only 2 before-chunks, no after-chunks")

    def test_panel_shows_figure_thumbnail_for_caption_chunk(self) -> None:
        diagram = DiagramAsset.objects.create(
            document=self.document, page=self.page,
            image_path="images/test/fig1.png", image_format="PNG",
            caption="Rail joint cross-section.",
        )
        caption_chunk = ContentChunk.objects.create(
            document=self.document, page=self.page,
            chunk_index=20, chunk_text="Rail joint cross-section.",
            chunk_type=ContentChunk.ChunkType.CAPTION,
            diagram_asset=diagram,
        )
        response = self.client.get(
            reverse("chunk-context-partial", args=[caption_chunk.id])
        )
        self.assertContains(response, "images/test/fig1.png")

    def test_nonexistent_chunk_returns_404(self) -> None:
        response = self.client.get(
            reverse("chunk-context-partial", args=[uuid.uuid4()])
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_access_redirects_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(
            reverse("chunk-context-partial", args=[self.chunks[0].id])
        )
        self.assertEqual(response.status_code, 302)

    def test_panel_shows_document_and_page_metadata(self) -> None:
        chunk = self.chunks[2]
        response = self.client.get(
            reverse("chunk-context-partial", args=[chunk.id])
        )
        self.assertContains(response, "RDSO Spec")
        self.assertContains(response, "42")  # page number