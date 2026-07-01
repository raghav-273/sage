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
from unittest import mock
from django.test import TestCase, override_settings 

from apps.portal.login_security import generate_challenge


class PortalAuthTests(TestCase):
    def setUp(self) -> None:
        # Same reasoning as AdaptiveLoginVerificationTests: failure counts
        # live in the cache, not the DB, so TestCase's transaction rollback
        # doesn't clear them between test classes. Without this, a prior
        # class's failed-login tests (e.g. test_tampered_challenge_token_is_rejected,
        # which deliberately never succeeds) leak an elevated failure count
        # into these tests, silently triggering the adaptive challenge here.
        cache.clear()
        
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
    def setUp(self) -> None:
        # Doesn't exercise login itself, so this isn't fixing an active bug —
        # added for defensive consistency, so this file doesn't quietly
        # regress the same way if a future test here ever does touch login.
        cache.clear()
    
    def test_document_detail_endpoint_rejects_anonymous_request(self) -> None:
        client = APIClient()
        response = client.get("/api/documents/00000000-0000-0000-0000-000000000000/")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_query_endpoint_rejects_anonymous_request(self) -> None:
        client = APIClient()
        response = client.post("/api/query/", {"query": "test"}, format="json")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

@override_settings(LOGIN_CHALLENGE_FAILURE_THRESHOLD=5)
class AdaptiveLoginVerificationTests(TestCase):
    """
    Tests apps.portal.login_security + apps.portal.turnstile's
    integration into PortalLoginView: no challenge under the threshold,
    Turnstile shown at/above it by default, and the two paths (no
    token, Cloudflare unreachable) that degrade to the plain-text
    fallback rather than hard-rejecting. verify_turnstile is mocked
    throughout — these test the view's branching logic, not Cloudflare's
    actual API; see tests/unit/test_turnstile.py for that.
    """

    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")

    def _fail_login(self, times: int) -> None:
        for _ in range(times):
            self.client.post(reverse("login"), {"username": "reviewer", "password": "wrong"})

    def test_no_challenge_below_threshold(self) -> None:
        self._fail_login(4)
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "cf-turnstile")

    def test_turnstile_widget_appears_at_threshold(self) -> None:
        self._fail_login(5)
        response = self.client.get(reverse("login"))
        self.assertContains(response, "cf-turnstile")
        self.assertContains(response, "data-sitekey")

    @mock.patch("apps.portal.views.verify_turnstile")
    def test_correct_credentials_with_verified_turnstile_succeeds(self, mock_verify) -> None:
        mock_verify.return_value = True
        self._fail_login(5)

        response = self.client.post(
            reverse("login"),
            {"username": "reviewer", "password": "test-pass-123", "cf-turnstile-response": "a-token"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    @mock.patch("apps.portal.views.verify_turnstile")
    def test_correct_credentials_with_rejected_turnstile_fails(self, mock_verify) -> None:
        mock_verify.return_value = False
        self._fail_login(5)

        response = self.client.post(
            reverse("login"),
            {"username": "reviewer", "password": "test-pass-123", "cf-turnstile-response": "a-bad-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_correct_credentials_with_no_token_offers_fallback(self) -> None:
        # No cf-turnstile-response at all — the accessibility path
        # (JS disabled/blocked), not a Cloudflare API failure.
        self._fail_login(5)

        response = self.client.post(
            reverse("login"), {"username": "reviewer", "password": "test-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fallback_challenge_token")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    @mock.patch("apps.portal.views.verify_turnstile")
    def test_cloudflare_unreachable_offers_fallback_not_hard_rejection(self, mock_verify) -> None:
        mock_verify.return_value = None  # simulates a network/timeout failure
        self._fail_login(5)

        response = self.client.post(
            reverse("login"),
            {"username": "reviewer", "password": "test-pass-123", "cf-turnstile-response": "a-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temporarily unavailable")
        self.assertContains(response, "fallback_challenge_token")

    def test_fallback_challenge_correct_answer_succeeds(self) -> None:
        self._fail_login(5)
        # First submission with no token triggers the fallback to render.
        first_response = self.client.post(
            reverse("login"), {"username": "reviewer", "password": "test-pass-123"},
        )
        question = first_response.context["fallback_challenge_question"]
        token = first_response.context["fallback_challenge_token"]

        arithmetic_match = re.search(r"What is (\d+) \+ (\d+)\?", question)
        if arithmetic_match:
            a, b = int(arithmetic_match.group(1)), int(arithmetic_match.group(2))
            answer = str(a + b)
        else:
            answer = re.search(r'"([A-Z]+)"', question).group(1)

        response = self.client.post(
            reverse("login"),
            {
                "username": "reviewer", "password": "test-pass-123",
                "fallback_challenge_answer": answer, "fallback_challenge_token": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_tampered_fallback_challenge_token_is_rejected(self) -> None:
        self._fail_login(5)
        self.client.post(reverse("login"), {"username": "reviewer", "password": "test-pass-123"})

        response = self.client.post(
            reverse("login"),
            {
                "username": "reviewer", "password": "test-pass-123",
                "fallback_challenge_answer": "7", "fallback_challenge_token": "not-a-real-token",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_successful_login_resets_failure_count(self) -> None:
        self._fail_login(4)  # below threshold — no challenge involved at all

        login_response = self.client.post(
            reverse("login"), {"username": "reviewer", "password": "test-pass-123"},
        )
        self.assertEqual(login_response.status_code, 302)

        self.client.post(reverse("logout"))
        self._fail_login(2)

        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "cf-turnstile")