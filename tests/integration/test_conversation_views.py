# tests/integration/test_conversation_views.py
"""Integration tests for the document conversation pages."""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.conversation.models import ConversationTurn
from apps.conversation.services import get_or_create_active_session
from apps.documents.models import Document


class DocumentConversationPageTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.document = Document.objects.create(
            name="Doc", original_filename="d.pdf", file_path="documents/d.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )

    def test_page_loads_with_no_history(self) -> None:
        response = self.client.get(reverse("document-conversation-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No questions asked yet")

    def test_non_ready_document_returns_404(self) -> None:
        pending_doc = Document.objects.create(
            name="Pending", original_filename="p.pdf", file_path="documents/p.pdf",
            file_size_bytes=1, status=Document.Status.PENDING,
        )
        response = self.client.get(reverse("document-conversation-page", args=[pending_doc.id]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_access_redirects_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("document-conversation-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 302)

    @mock.patch("apps.portal.views.ask_in_session")
    def test_submit_creates_turn_and_returns_fragment(self, mock_ask) -> None:
        mock_ask.return_value = ConversationTurn(
            turn_index=0, query_text="a question", answer_text="an answer [1]",
            has_valid_citations=True, retrieved_chunk_count=1,
        )

        response = self.client.post(
            reverse("document-conversation-submit", args=[self.document.id]), {"query": "a question"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "a question")
        self.assertContains(response, "Verified")

    def test_empty_query_shows_error_without_calling_ask_in_session(self) -> None:
        with mock.patch("apps.portal.views.ask_in_session") as mock_ask:
            response = self.client.post(
                reverse("document-conversation-submit", args=[self.document.id]), {"query": "  "},
            )
            mock_ask.assert_not_called()
        self.assertContains(response, "Please enter a question")

    def test_clear_deactivates_session_and_redirects(self) -> None:
        session = get_or_create_active_session(self.document, self.user)

        response = self.client.post(reverse("document-conversation-clear", args=[self.document.id]))

        self.assertRedirects(response, reverse("document-conversation-page", args=[self.document.id]))
        session.refresh_from_db()
        self.assertFalse(session.is_active)

    @mock.patch("apps.portal.views.ask_in_session")
    def test_rate_limit_blocks_after_threshold(self, mock_ask) -> None:
        mock_ask.return_value = ConversationTurn(
            turn_index=0, query_text="q", answer_text="a [1]",
            has_valid_citations=True, retrieved_chunk_count=1,
        )

        for _ in range(8):
            self.client.post(
                reverse("document-conversation-submit", args=[self.document.id]), {"query": "q"},
            )

        response = self.client.post(
            reverse("document-conversation-submit", args=[self.document.id]), {"query": "one more"},
        )
        self.assertContains(response, "Too many questions")