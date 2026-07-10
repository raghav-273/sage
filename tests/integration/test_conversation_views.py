# tests/integration/test_conversation_views.py
"""Integration tests for the investigation workspace views."""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.conversation.models import ConversationTurn, DocumentSession
from apps.conversation.services import get_or_create_active_session
from apps.documents.models import Document


class InvestigationStartTests(TestCase):
    """Tests for the 'no active session' state and starting a new investigation."""

    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.document = Document.objects.create(
            name="RDSO Spec", original_filename="rdso.pdf",
            file_path="documents/rdso.pdf", file_size_bytes=1,
            status=Document.Status.READY,
        )

    def test_get_without_session_shows_start_form(self) -> None:
        response = self.client.get(reverse("document-conversation-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start Investigation")
        self.assertContains(response, "Investigation title")

    def test_post_with_title_creates_session_and_redirects(self) -> None:
        response = self.client.post(
            reverse("document-conversation-page", args=[self.document.id]),
            {"title": "Track Gauge Compliance Review"},
        )
        self.assertRedirects(response, reverse("document-conversation-page", args=[self.document.id]))
        session = DocumentSession.objects.get(document=self.document, user=self.user, is_active=True)
        self.assertEqual(session.title, "Track Gauge Compliance Review")

    def test_post_without_title_uses_fallback(self) -> None:
        self.client.post(
            reverse("document-conversation-page", args=[self.document.id]),
            {"title": ""},
        )
        session = DocumentSession.objects.get(document=self.document, user=self.user, is_active=True)
        self.assertIn("Investigation", session.title)

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


class InvestigationWorkspaceTests(TestCase):
    """Tests for the investigation workspace (active session exists)."""

    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.document = Document.objects.create(
            name="RDSO Spec", original_filename="rdso.pdf",
            file_path="documents/rdso.pdf", file_size_bytes=1,
            status=Document.Status.READY,
        )
        self.session = DocumentSession.objects.create(
            document=self.document, user=self.user, is_active=True,
            title="Track Gauge Review",
        )

    def test_workspace_shows_investigation_title(self) -> None:
        response = self.client.get(reverse("document-conversation-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Track Gauge Review")
        self.assertContains(response, "No findings recorded yet")

    def test_workspace_shows_existing_findings(self) -> None:
        ConversationTurn.objects.create(
            session=self.session, turn_index=0,
            query_text="What is the minimum gauge?",
            answer_text="The minimum gauge is 1435 mm. [1]",
            has_valid_citations=True, retrieved_chunk_count=1, citations=[],
        )
        response = self.client.get(reverse("document-conversation-page", args=[self.document.id]))
        self.assertContains(response, "What is the minimum gauge?")
        self.assertContains(response, "1435 mm")

    @mock.patch("apps.portal.views.ask_in_session")
    def test_submit_finding_returns_fragment(self, mock_ask) -> None:
        mock_ask.return_value = ConversationTurn(
            turn_index=0, query_text="a question",
            answer_text="an answer [1]", has_valid_citations=True,
            retrieved_chunk_count=1,
        )
        response = self.client.post(
            reverse("document-conversation-submit", args=[self.document.id]),
            {"query": "What is the track gauge requirement?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "a question")
        self.assertContains(response, "Verified")

    def test_empty_query_rejected(self) -> None:
        with mock.patch("apps.portal.views.ask_in_session") as mock_ask:
            response = self.client.post(
                reverse("document-conversation-submit", args=[self.document.id]),
                {"query": "   "},
            )
            mock_ask.assert_not_called()
        self.assertContains(response, "Please enter a question")

    def test_clear_deactivates_session_and_redirects(self) -> None:
        response = self.client.post(reverse("document-conversation-clear", args=[self.document.id]))
        self.assertRedirects(response, reverse("document-conversation-page", args=[self.document.id]))
        self.session.refresh_from_db()
        self.assertFalse(self.session.is_active)

    def test_export_pdf_returns_pdf_content_type(self) -> None:
        response = self.client.get(reverse("investigation-export-pdf", args=[self.document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        self.assertTrue(response.content.startswith(b"%PDF"))

    @mock.patch("apps.portal.views.ask_in_session")
    def test_rate_limit_blocks_after_threshold(self, mock_ask) -> None:
        mock_ask.return_value = ConversationTurn(
            turn_index=0, query_text="q", answer_text="a",
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