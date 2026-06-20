# services/llm_client/gemini_generation_client.py
"""
Gemini generation client using the unified Google Gen AI SDK (`google-genai`).

Model is configurable via GEMINI_MODEL (default: gemini-2.5-flash, free tier).
"""

from __future__ import annotations

import os

from google import genai
from google.genai import errors, types

from .generation_base import GenerationClient, GenerationError, RetryableGenerationError

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class GeminiGenerationClient(GenerationClient):
    """Generation client for Google's Gemini API."""

    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise GenerationError(
                "GEMINI_API_KEY is not set and no api_key was provided"
            )
        self._client = genai.Client(api_key=resolved_key)
        self._model = model or os.environ.get("GEMINI_MODEL") or self.DEFAULT_MODEL

    def _generate_once(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )
        except errors.APIError as exc:
            if exc.code in _RETRYABLE_STATUS_CODES:
                raise RetryableGenerationError(str(exc)) from exc
            raise GenerationError(f"Gemini generation request failed: {exc}") from exc
        except Exception as exc:
            raise GenerationError(f"Unexpected Gemini client error: {exc}") from exc

        if not response.text:
            raise GenerationError("Gemini returned an empty response")

        return response.text