# services/llm_client/gemini_generation_client.py
"""
Gemini generation client using the unified Google Gen AI SDK (`google-genai`).

Two reliability layers added in response to a directly observed,
reproduced failure: gemini-2.5-flash's free tier intermittently returns
503 UNAVAILABLE ("high demand") even after the base class's full
5-attempt exponential backoff retry policy is exhausted. This is a
widely-reported, ongoing issue across Gemini's Flash models — confirmed
via Google's own developer forum and the python-genai GitHub repo,
spanning late 2025 through mid-2026 — not specific to this deployment or
API key, and it affects free and paid tiers equally.

1. Model fallback: if every retry against the primary model
   (GEMINI_MODEL) fails, one additional full retry cycle is attempted
   against a separate, smaller free-tier model (GEMINI_FALLBACK_MODEL,
   default gemini-2.5-flash-lite). A different model has an independent
   capacity pool, so a demand spike specific to one model often doesn't
   affect the other — this is the standard, community-recommended
   mitigation order for 503 errors: backoff retry, then model fallback.

2. Outer request timeout: HttpOptions(timeout=...) is set on the Client
   as a first line of defense (the documented way to do this), but is
   NOT trusted alone — multiple open issues against google-genai
   (#1893, #4031, #911) document that this is not reliably honored in
   all code paths; under load, a request can stall at the socket level
   indefinitely with no exception raised at all. A ThreadPoolExecutor-
   based outer timeout guarantees this client gives up and retries
   within a bounded time regardless of whether the SDK's own timeout
   fires. shutdown(wait=False) is essential: a hung background thread
   cannot be forcibly killed in Python, and blocking on it during
   cleanup would reintroduce the exact hang this exists to prevent.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os

from google import genai
from google.genai import errors, types

from .generation_base import GenerationClient, GenerationError, RetryableGenerationError

logger = logging.getLogger("services.llm_client.gemini_generation_client")

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class GeminiGenerationClient(GenerationClient):
    """Generation client for Google's Gemini API, with model fallback and an outer timeout guard."""

    DEFAULT_MODEL = "gemini-2.5-flash"
    DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash-lite"
    DEFAULT_REQUEST_TIMEOUT_SECONDS = 25

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        request_timeout_seconds: float | None = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise GenerationError(
                "GEMINI_API_KEY is not set and no api_key was provided"
            )

        self._request_timeout_seconds = request_timeout_seconds or float(
            os.environ.get("GEMINI_REQUEST_TIMEOUT_SECONDS", self.DEFAULT_REQUEST_TIMEOUT_SECONDS)
        )

        # Documented placement for HttpOptions is the Client constructor,
        # not per-call config. Kept despite the known reliability gaps
        # described in the module docstring — it costs nothing and likely
        # helps in many cases; the ThreadPoolExecutor below is the
        # guaranteed backstop, not this.
        self._client = genai.Client(
            api_key=resolved_key,
            http_options=types.HttpOptions(timeout=int(self._request_timeout_seconds * 1000)),
        )
        self._model = model or os.environ.get("GEMINI_MODEL") or self.DEFAULT_MODEL
        self._fallback_model = (
            fallback_model
            or os.environ.get("GEMINI_FALLBACK_MODEL")
            or self.DEFAULT_FALLBACK_MODEL
        )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """
        Tries the primary model first, with the base class's full
        retry/backoff policy. If every attempt against the primary model
        fails, makes one additional full retry cycle against a separate
        fallback model before giving up.
        """
        try:
            return super().generate(system_prompt, user_prompt, temperature, max_output_tokens)
        except GenerationError as primary_error:
            if self._fallback_model == self._model:
                raise  # no distinct fallback configured; nothing else to try

            logger.warning(
                "gemini_primary_model_exhausted model=%s fallback_model=%s error=%s",
                self._model, self._fallback_model, primary_error,
            )
            original_model = self._model
            try:
                self._model = self._fallback_model
                return super().generate(system_prompt, user_prompt, temperature, max_output_tokens)
            except GenerationError as fallback_error:
                raise GenerationError(
                    f"Both primary model '{original_model}' and fallback model "
                    f"'{self._fallback_model}' failed. "
                    f"Primary: {primary_error}. Fallback: {fallback_error}"
                ) from fallback_error
            finally:
                self._model = original_model

    def _generate_once(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        def _call():
            return self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(_call)
            response = future.result(timeout=self._request_timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise RetryableGenerationError(
                f"Gemini request to model '{self._model}' exceeded the "
                f"{self._request_timeout_seconds}s outer timeout"
            ) from exc
        except errors.APIError as exc:
            if exc.code in _RETRYABLE_STATUS_CODES:
                raise RetryableGenerationError(str(exc)) from exc
            raise GenerationError(f"Gemini generation request failed: {exc}") from exc
        except Exception as exc:
            raise GenerationError(f"Unexpected Gemini client error: {exc}") from exc
        finally:
            # wait=False: do not block here waiting for a possibly-hung
            # background thread to finish. See module docstring.
            executor.shutdown(wait=False)

        if not response.text:
            raise GenerationError("Gemini returned an empty response")

        return response.text