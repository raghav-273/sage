# services/llm_client/generation_base.py
"""
Common interface for answer-generation providers (Gemini; future: Ollama,
NVIDIA NIM).

GenerationClient mirrors EmbeddingClient's template-method shape but has
a distinct contract: generate(prompt) -> text, not embed(texts) -> vectors.
Kept in its own file so the existing, validated EmbeddingClient in base.py
is never touched.

Provider selection is environment-driven via get_generation_client().
Adding a provider means adding one client class and one branch in the
factory below — callers never reference a concrete class.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod

logger = logging.getLogger("services.llm_client.generation")


class GenerationError(Exception):
    """Raised when generation fails after all retries, or for a non-retryable reason."""


class RetryableGenerationError(Exception):
    """
    Raised internally by subclasses for transient failures (rate limits,
    timeouts, 5xx errors). Caught by the base class's retry loop; never
    propagates to the caller of generate().
    """


class GenerationClient(ABC):
    """Abstract base class for answer-generation providers."""

    DEFAULT_TEMPERATURE: float = 0.0
    DEFAULT_MAX_OUTPUT_TOKENS: int = 1024

    MAX_RETRIES: int = 5
    INITIAL_BACKOFF_SECONDS: float = 1.0

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """
        Generate a response for the given prompts, with retry/backoff
        applied uniformly across providers.

        Raises:
            GenerationError: if generation fails after MAX_RETRIES attempts.
        """
        resolved_temperature = (
            self.DEFAULT_TEMPERATURE if temperature is None else temperature
        )
        resolved_max_tokens = (
            self.DEFAULT_MAX_OUTPUT_TOKENS if max_output_tokens is None else max_output_tokens
        )

        backoff = self.INITIAL_BACKOFF_SECONDS
        last_exc: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return self._generate_once(
                    system_prompt, user_prompt, resolved_temperature, resolved_max_tokens
                )
            except RetryableGenerationError as exc:
                last_exc = exc
                if attempt == self.MAX_RETRIES:
                    break
                logger.warning(
                    "generation_retry attempt=%d/%d backoff=%.1fs error=%s",
                    attempt, self.MAX_RETRIES, backoff, exc,
                )
                time.sleep(backoff)
                backoff *= 2

        raise GenerationError(
            f"Generation failed after {self.MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    @abstractmethod
    def _generate_once(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        """
        Perform exactly one provider API call.

        Implementations must raise RetryableGenerationError for transient
        failures, and GenerationError directly for non-retryable failures
        (invalid API key, malformed request, etc.).
        """
        raise NotImplementedError


def get_generation_client() -> GenerationClient:
    """
    Environment-driven provider factory.

    Reads GENERATION_PROVIDER to select a concrete GenerationClient.
    Adding a new provider requires one new branch here and one new
    client class — no changes to any caller.

    Raises:
        GenerationError: if GENERATION_PROVIDER is unset, unrecognized,
            or the selected provider's required configuration is missing.
    """
    provider = os.environ.get("GENERATION_PROVIDER", "").strip().lower()

    if provider == "gemini":
        from .gemini_generation_client import GeminiGenerationClient

        return GeminiGenerationClient()

    if not provider:
        raise GenerationError(
            "GENERATION_PROVIDER is not set. Set it to a supported provider (e.g. 'gemini')."
        )

    raise GenerationError(
        f"Unsupported GENERATION_PROVIDER='{provider}'. Supported providers: 'gemini'."
    )