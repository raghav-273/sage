# tests/unit/test_gemini_generation_client.py
"""
Unit tests for GeminiGenerationClient's model-fallback and outer-timeout
behavior. Mocks at the GenerationClient.generate level (for fallback
logic) and at the underlying SDK call level (for the timeout guard) —
no real API calls.
"""

from __future__ import annotations

import time
import unittest
from unittest import mock

from services.llm_client.generation_base import GenerationClient, GenerationError, RetryableGenerationError
from services.llm_client.gemini_generation_client import GeminiGenerationClient


class GeminiFallbackModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GeminiGenerationClient(
            api_key="test-key-not-real", model="gemini-2.5-flash", fallback_model="gemini-2.5-flash-lite",
        )

    @mock.patch.object(GenerationClient, "generate")
    def test_primary_success_never_touches_fallback(self, mock_super_generate) -> None:
        mock_super_generate.return_value = "primary answer"

        result = self.client.generate("system", "user")

        self.assertEqual(result, "primary answer")
        self.assertEqual(mock_super_generate.call_count, 1)
        self.assertEqual(self.client._model, "gemini-2.5-flash")

    @mock.patch.object(GenerationClient, "generate")
    def test_primary_failure_falls_back_and_succeeds(self, mock_super_generate) -> None:
        mock_super_generate.side_effect = [GenerationError("primary exhausted"), "fallback answer"]

        result = self.client.generate("system", "user")

        self.assertEqual(result, "fallback answer")
        self.assertEqual(mock_super_generate.call_count, 2)

    @mock.patch.object(GenerationClient, "generate")
    def test_model_attribute_restored_after_fallback_succeeds(self, mock_super_generate) -> None:
        mock_super_generate.side_effect = [GenerationError("primary exhausted"), "fallback answer"]

        self.client.generate("system", "user")

        self.assertEqual(self.client._model, "gemini-2.5-flash")

    @mock.patch.object(GenerationClient, "generate")
    def test_model_attribute_restored_even_if_fallback_also_fails(self, mock_super_generate) -> None:
        mock_super_generate.side_effect = [
            GenerationError("primary exhausted"), GenerationError("fallback also exhausted"),
        ]

        with self.assertRaises(GenerationError):
            self.client.generate("system", "user")

        self.assertEqual(self.client._model, "gemini-2.5-flash")

    @mock.patch.object(GenerationClient, "generate")
    def test_both_models_failing_raises_combined_error_message(self, mock_super_generate) -> None:
        mock_super_generate.side_effect = [
            GenerationError("primary down"), GenerationError("fallback down"),
        ]

        with self.assertRaises(GenerationError) as ctx:
            self.client.generate("system", "user")

        self.assertIn("primary down", str(ctx.exception))
        self.assertIn("fallback down", str(ctx.exception))

    def test_no_fallback_configured_raises_immediately_on_primary_failure(self) -> None:
        client = GeminiGenerationClient(
            api_key="test-key-not-real", model="gemini-2.5-flash", fallback_model="gemini-2.5-flash",
        )
        with mock.patch.object(GenerationClient, "generate") as mock_generate:
            mock_generate.side_effect = GenerationError("primary exhausted")
            with self.assertRaises(GenerationError):
                client.generate("system", "user")
            self.assertEqual(mock_generate.call_count, 1)


class GeminiOuterTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GeminiGenerationClient(
            api_key="test-key-not-real", model="gemini-2.5-flash",
            fallback_model="gemini-2.5-flash", request_timeout_seconds=0.2,
        )

    def test_hung_request_raises_retryable_not_a_silent_hang(self) -> None:
        """
        Simulates the documented googleapis/python-genai#1893 failure mode:
        a request that never returns and never raises. Confirms the outer
        ThreadPoolExecutor timeout catches this — without it, this test
        would hang for as long as _hanging_call's sleep, or forever.
        """
        def _hanging_call(*args, **kwargs):
            time.sleep(5)  # far longer than the 0.2s configured timeout
            return mock.Mock(text="should never be reached")

        with mock.patch.object(
            self.client._client.models, "generate_content", side_effect=_hanging_call
        ):
            with self.assertRaises(RetryableGenerationError):
                self.client._generate_once("system", "user", 0.0, 1024)

    def test_fast_response_within_timeout_succeeds_normally(self) -> None:
        mock_response = mock.Mock(text="a normal answer")
        with mock.patch.object(
            self.client._client.models, "generate_content", return_value=mock_response
        ):
            result = self.client._generate_once("system", "user", 0.0, 1024)
        self.assertEqual(result, "a normal answer")