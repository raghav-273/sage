# tests/unit/test_image_captioner.py
"""Unit tests for services.generation.image_captioner. No real Gemini calls."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.generation.image_captioner import generate_caption


class GenerateCaptionTests(unittest.TestCase):
    def _write_temp_image(self, content: bytes = b"fake png") -> Path:
        f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_missing_file_returns_none(self) -> None:
        result = generate_caption(Path("/nonexistent/image.png"))
        self.assertIsNone(result)

    def test_missing_api_key_returns_none(self) -> None:
        path = self._write_temp_image()
        try:
            with mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
                import os; os.environ.pop("GEMINI_API_KEY", None)
                result = generate_caption(path, api_key=None)
            self.assertIsNone(result)
        finally:
            path.unlink(missing_ok=True)

    def test_empty_file_returns_none(self) -> None:
        path = self._write_temp_image(content=b"")
        try:
            result = generate_caption(path, api_key="test-key")
            self.assertIsNone(result)
        finally:
            path.unlink(missing_ok=True)

    def test_api_error_returns_none_not_raised(self) -> None:
        path = self._write_temp_image()
        try:
            with mock.patch("services.generation.image_captioner.genai") as mock_genai:
                mock_client = mock.MagicMock()
                mock_genai.Client.return_value = mock_client
                mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE")
                result = generate_caption(path, api_key="test-key")
            self.assertIsNone(result)
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
        expected = "Cross-section of a rail joint assembly showing bolt positions and clearances."
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