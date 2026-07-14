# tests/unit/test_image_captioner.py
"""Unit tests for services.generation.image_captioner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.generation.image_captioner import (
    CaptionError,
    QuotaExhaustedError,
    generate_caption,
)


class GenerateCaptionTests(unittest.TestCase):
    def _write_temp_image(self, content: bytes = b"fake png content") -> Path:
        f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_missing_file_returns_none(self) -> None:
        result = generate_caption(Path("/nonexistent/image.png"), api_key="test-key")
        self.assertIsNone(result)

    def test_missing_api_key_raises_caption_error(self) -> None:
        """No API key configured — raises CaptionError (not returns None)."""
        path = self._write_temp_image()
        try:
            import os
            old_key = os.environ.pop("GEMINI_API_KEY", None)
            with self.assertRaises(CaptionError):
                generate_caption(path, api_key=None)
        finally:
            if old_key is not None:
                os.environ["GEMINI_API_KEY"] = old_key
            path.unlink(missing_ok=True)

    def test_empty_file_returns_none(self) -> None:
        path = self._write_temp_image(content=b"")
        try:
            result = generate_caption(path, api_key="test-key")
            self.assertIsNone(result)
        finally:
            path.unlink(missing_ok=True)

    def test_api_503_raises_caption_error(self) -> None:
        """
        Non-quota API errors raise CaptionError (not QuotaExhaustedError).
        The caption task catches CaptionError and marks the record FAILED
        without retrying.
        """
        path = self._write_temp_image()
        try:
            with mock.patch("services.generation.image_captioner.genai") as mock_genai:
                mock_client = mock.MagicMock()
                mock_genai.Client.return_value = mock_client
                mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE")
                with self.assertRaises(CaptionError):
                    generate_caption(path, api_key="test-key")
        finally:
            path.unlink(missing_ok=True)

    def test_api_429_raises_quota_exhausted_error(self) -> None:
        """
        429 quota errors must raise QuotaExhaustedError so the caption
        task can apply backoff retry rather than marking the record FAILED.

        The Google GenAI SDK's APIError cannot be constructed directly in
        tests (its __init__ requires an internal HTTP response object).
        Two approaches are tested:
        1. A real APIError raised through the SDK's own raise mechanism
           (not possible without an HTTP response fixture)
        2. A plain Exception whose string representation contains '429'
           (what the SDK may emit in some error paths)

        This test uses approach 2 because it tests the contract
        (QuotaExhaustedError is raised on quota exhaustion) without
        depending on SDK internals that are not part of the public API.
        The production code handles both paths.
        """
        path = self._write_temp_image()
        try:
            with mock.patch("services.generation.image_captioner.genai") as mock_genai:
                mock_client = mock.MagicMock()
                mock_genai.Client.return_value = mock_client
                # Simulate what the SDK emits for a 429 when APIError
                # cannot be raised directly: a plain Exception whose
                # string representation contains the quota error markers.
                mock_client.models.generate_content.side_effect = Exception(
                    "429 RESOURCE_EXHAUSTED: Quota exceeded for default-flash."
                )
                with self.assertRaises(QuotaExhaustedError):
                    generate_caption(path, api_key="test-key")
        finally:
            path.unlink(missing_ok=True)

    def test_api_429_via_errors_module_raises_quota_exhausted_error(self) -> None:
        """
        Complementary test: if the SDK does raise errors.APIError with
        code=429, QuotaExhaustedError is still raised.

        Patches errors.APIError with a real exception class that can be
        raised, rather than trying to construct the SDK's APIError directly.
        """
        path = self._write_temp_image()

        class FakeAPIError(Exception):
            """Stands in for google.genai.errors.APIError in this test."""
            def __init__(self, code: int, message: str) -> None:
                super().__init__(message)
                self.code = code

        try:
            with mock.patch("services.generation.image_captioner.genai") as mock_genai, \
                 mock.patch("services.generation.image_captioner.errors") as mock_errors:

                mock_errors.APIError = FakeAPIError
                mock_client = mock.MagicMock()
                mock_genai.Client.return_value = mock_client
                mock_client.models.generate_content.side_effect = FakeAPIError(
                    429, "RESOURCE_EXHAUSTED"
                )
                with self.assertRaises(QuotaExhaustedError):
                    generate_caption(path, api_key="test-key")
        finally:
            path.unlink(missing_ok=True)

    def test_api_non_quota_error_raises_caption_error(self) -> None:
        """
        Non-quota API errors (503, 404, etc.) raise CaptionError, not
        QuotaExhaustedError, so the caption task marks them FAILED
        without scheduling a retry.
        """
        path = self._write_temp_image()

        class FakeAPIError(Exception):
            def __init__(self, code: int, message: str) -> None:
                super().__init__(message)
                self.code = code

        try:
            with mock.patch("services.generation.image_captioner.genai") as mock_genai, \
                 mock.patch("services.generation.image_captioner.errors") as mock_errors:

                mock_errors.APIError = FakeAPIError
                mock_client = mock.MagicMock()
                mock_genai.Client.return_value = mock_client
                mock_client.models.generate_content.side_effect = FakeAPIError(
                    503, "Service Unavailable"
                )
                with self.assertRaises(CaptionError) as ctx:
                    generate_caption(path, api_key="test-key")
                # Must be CaptionError, not the subclass QuotaExhaustedError
                self.assertNotIsInstance(ctx.exception, QuotaExhaustedError)
        finally:
            path.unlink(missing_ok=True)

    def test_no_caption_sentinel_returns_none(self) -> None:
        path = self._write_temp_image()
        try:
            with mock.patch("services.generation.image_captioner.genai") as mock_genai:
                mock_client = mock.MagicMock()
                mock_genai.Client.return_value = mock_client
                mock_response = mock.MagicMock()
                mock_response.text = "NO_CAPTION"
                mock_client.models.generate_content.return_value = mock_response
                result = generate_caption(path, api_key="test-key")
            self.assertIsNone(result)
        finally:
            path.unlink(missing_ok=True)

    def test_successful_caption_returned(self) -> None:
        path = self._write_temp_image()
        expected = "Cross-section of a rail joint assembly showing bolt positions."
        try:
            with mock.patch("services.generation.image_captioner.genai") as mock_genai:
                mock_client = mock.MagicMock()
                mock_genai.Client.return_value = mock_client
                mock_response = mock.MagicMock()
                mock_response.text = expected
                mock_client.models.generate_content.return_value = mock_response
                result = generate_caption(path, api_key="test-key")
            self.assertEqual(result, expected)
        finally:
            path.unlink(missing_ok=True)

    def test_whitespace_only_response_returns_none(self) -> None:
        path = self._write_temp_image()
        try:
            with mock.patch("services.generation.image_captioner.genai") as mock_genai:
                mock_client = mock.MagicMock()
                mock_genai.Client.return_value = mock_client
                mock_response = mock.MagicMock()
                mock_response.text = "   "
                mock_client.models.generate_content.return_value = mock_response
                result = generate_caption(path, api_key="test-key")
            self.assertIsNone(result)
        finally:
            path.unlink(missing_ok=True)