# tests/integration/test_portal_auth.py
"""
Integration tests for portal authentication: login, logout, route
protection, the API-wide permission change, and adaptive login
verification (Milestone 9A follow-up).
"""

from __future__ import annotations

import re

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.portal.login_security import generate_challenge


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


class AdaptiveLoginVerificationTests(TestCase):
    """
    Tests apps.portal.login_security's integration into PortalLoginView:
    no challenge under the threshold, a challenge appears at/above it,
    and it's actually enforced — not just displayed.
    """

    def setUp(self) -> None:
        # Failure counts live in the cache, not the DB — TestCase's
        # transaction rollback doesn't clear this, so it must be done
        # explicitly or counts leak between test methods.
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")

    def _fail_login(self, times: int) -> None:
        for _ in range(times):
            self.client.post(reverse("login"), {"username": "reviewer", "password": "wrong"})

    def test_no_challenge_below_threshold(self) -> None:
        self._fail_login(4)  # default threshold is 5
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "What is")

    def test_challenge_appears_at_threshold(self) -> None:
        self._fail_login(5)
        response = self.client.get(reverse("login"))
        self.assertContains(response, "What is")

    def test_correct_credentials_rejected_without_challenge_answer(self) -> None:
        self._fail_login(5)
        response = self.client.post(
            reverse("login"), {"username": "reviewer", "password": "test-pass-123"},
        )
        self.assertEqual(response.status_code, 200)  # re-rendered, not logged in
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_correct_credentials_and_correct_challenge_succeeds(self) -> None:
        self._fail_login(5)
        question, token = generate_challenge()
        match = re.search(r"What is (\d+) \+ (\d+)\?", question)
        a, b = int(match.group(1)), int(match.group(2))

        response = self.client.post(
            reverse("login"),
            {
                "username": "reviewer",
                "password": "test-pass-123",
                "challenge_answer": str(a + b),
                "challenge_token": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_correct_credentials_with_wrong_challenge_answer_fails(self) -> None:
        self._fail_login(5)
        _, token = generate_challenge()

        response = self.client.post(
            reverse("login"),
            {
                "username": "reviewer",
                "password": "test-pass-123",
                "challenge_answer": "999999",
                "challenge_token": token,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_tampered_challenge_token_is_rejected(self) -> None:
        self._fail_login(5)

        response = self.client.post(
            reverse("login"),
            {
                "username": "reviewer",
                "password": "test-pass-123",
                "challenge_answer": "7",
                "challenge_token": "not-a-real-signed-token",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_successful_login_resets_failure_count(self) -> None:
        self._fail_login(4)  # below threshold

        login_response = self.client.post(
            reverse("login"), {"username": "reviewer", "password": "test-pass-123"},
        )
        self.assertEqual(login_response.status_code, 302)

        # If the count had NOT reset on success, two more failures would
        # put it at 6 — over threshold. Since it resets, two more shouldn't
        # trigger the challenge yet.
        self.client.post(reverse("logout"))
        self._fail_login(2)

        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "What is")