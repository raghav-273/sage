# tests/unit/test_turnstile.py
"""
Unit tests for apps.portal.turnstile.verify_turnstile. Mocks
urllib.request.urlopen directly — no real network calls.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
from unittest import mock

from apps.portal.turnstile import verify_turnstile


def _mock_response(payload: dict) -> mock.MagicMock:
    response = mock.MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    return response


class VerifyTurnstileTests(unittest.TestCase):
    def test_empty_token_returns_false_without_network_call(self) -> None:
        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            result = verify_turnstile("", "127.0.0.1")
        self.assertFalse(result)
        mock_urlopen.assert_not_called()

    @mock.patch("urllib.request.urlopen")
    def test_successful_verification_returns_true(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _mock_response({"success": True})
        self.assertTrue(verify_turnstile("a-real-token", "127.0.0.1"))

    @mock.patch("urllib.request.urlopen")
    def test_rejected_verification_returns_false(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _mock_response(
            {"success": False, "error-codes": ["invalid-input-response"]}
        )
        self.assertFalse(verify_turnstile("a-bad-token", "127.0.0.1"))

    @mock.patch("urllib.request.urlopen")
    def test_network_error_returns_none_not_false(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        result = verify_turnstile("a-token", "127.0.0.1")
        self.assertIsNone(result)  # distinct from a definite rejection

    @mock.patch("urllib.request.urlopen")
    def test_malformed_response_returns_none(self, mock_urlopen) -> None:
        response = mock.MagicMock()
        response.read.return_value = b"not json"
        response.__enter__.return_value = response
        mock_urlopen.return_value = response
        self.assertIsNone(verify_turnstile("a-token", "127.0.0.1"))

    def test_missing_secret_key_returns_none(self) -> None:
        with mock.patch("apps.portal.turnstile.settings.TURNSTILE_SECRET_KEY", ""):
            result = verify_turnstile("a-token", "127.0.0.1")
        self.assertIsNone(result)