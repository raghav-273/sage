# tests/integration/test_portal_auth.py
"""
Integration tests for portal authentication: login, logout, route
protection, and confirmation that the API-wide permission change actually
took effect.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


class PortalAuthTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")

    def test_anonymous_dashboard_access_redirects_to_login(self) -> None:
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_valid_login_redirects_to_dashboard_and_grants_access(self) -> None:
        login_response = self.client.post(
            reverse("login"), {"username": "reviewer", "password": "test-pass-123"},
        )
        self.assertEqual(login_response.status_code, 302)

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "reviewer")

    def test_invalid_login_shows_error_and_does_not_authenticate(self) -> None:
        response = self.client.post(
            reverse("login"), {"username": "reviewer", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incorrect username or password")

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 302)

    def test_logout_clears_session(self) -> None:
        self.client.login(username="reviewer", password="test-pass-123")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

        self.client.post(reverse("logout"))

        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)


class ApiRequiresAuthenticationTests(TestCase):
    """Confirms the global IsAuthenticated change actually took effect."""

    def test_document_detail_endpoint_rejects_anonymous_request(self) -> None:
        client = APIClient()
        response = client.get("/api/documents/00000000-0000-0000-0000-000000000000/")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_query_endpoint_rejects_anonymous_request(self) -> None:
        client = APIClient()
        response = client.post("/api/query/", {"query": "test"}, format="json")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))