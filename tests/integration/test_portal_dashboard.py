# tests/integration/test_portal_dashboard.py
"""Integration tests for the dashboard: document table, search/filter, health section."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.chunks.models import ContentChunk
from apps.documents.models import Document, DocumentPage
from apps.portal.health import HealthStatus


class DashboardContentTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")

    def test_dashboard_lists_documents(self) -> None:
        Document.objects.create(
            name="Visible Doc", original_filename="visible.pdf", file_path="documents/visible.pdf",
            file_size_bytes=100, status=Document.Status.READY, page_count=10,
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Doc")

    def test_dashboard_shows_total_and_ready_counts(self) -> None:
        Document.objects.create(
            name="Ready Doc", original_filename="r.pdf", file_path="documents/r.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        Document.objects.create(
            name="Pending Doc", original_filename="p.pdf", file_path="documents/p.pdf",
            file_size_bytes=1, status=Document.Status.PENDING,
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["total_documents"], 2)
        self.assertEqual(response.context["ready_documents"], 1)

    def test_search_filters_by_name(self) -> None:
        Document.objects.create(
            name="Rail Joint Spec", original_filename="a.pdf", file_path="documents/a.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        Document.objects.create(
            name="Signal Manual", original_filename="b.pdf", file_path="documents/b.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        response = self.client.get(reverse("dashboard"), {"q": "Rail"})
        self.assertContains(response, "Rail Joint Spec")
        self.assertNotContains(response, "Signal Manual")

    def test_status_filter(self) -> None:
        Document.objects.create(
            name="Failed Doc", original_filename="f.pdf", file_path="documents/f.pdf",
            file_size_bytes=1, status=Document.Status.FAILED,
        )
        Document.objects.create(
            name="Ready Doc", original_filename="g.pdf", file_path="documents/g.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        response = self.client.get(reverse("dashboard"), {"status": Document.Status.FAILED})
        self.assertContains(response, "Failed Doc")
        self.assertNotContains(response, "Ready Doc")

    def test_chunk_count_displayed_correctly(self) -> None:
        document = Document.objects.create(
            name="Chunked Doc", original_filename="c.pdf", file_path="documents/c.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        page = DocumentPage.objects.create(document=document, page_number=1, raw_text="x")
        ContentChunk.objects.create(document=document, page=page, chunk_index=0, chunk_text="a")
        ContentChunk.objects.create(document=document, page=page, chunk_index=1, chunk_text="b")

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["page_obj"][0].chunk_count, 2)

    def test_empty_state_message(self) -> None:
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "No documents found")


class DashboardHealthSectionTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")

    @mock.patch("apps.portal.views.get_system_health")
    def test_health_checks_rendered(self, mock_health) -> None:
        mock_health.return_value = [
            HealthStatus(name="PostgreSQL", healthy=True),
            HealthStatus(name="Redis", healthy=True),
            HealthStatus(name="Celery Worker", healthy=False, detail="No workers responded"),
        ]
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "PostgreSQL")
        self.assertContains(response, "No workers responded")

    def test_real_postgres_check_succeeds(self) -> None:
        # Exercises the real SELECT 1 against the test database — no
        # external dependency to fake here, so a real pass is more
        # convincing than a mocked one.
        from apps.portal.health import check_postgres
        self.assertTrue(check_postgres().healthy)