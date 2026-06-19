# services/llm_client/base.py
"""
Common interface for embedding providers (OpenAI, Gemini).

EmbeddingClient is a template-method base class:
    - embed() is the public entry point. Splits an arbitrary-length list
      of texts into provider-sized batches and applies retry logic with
      exponential backoff uniformly across providers.
    - _embed_batch() is implemented by each subclass and performs exactly
      one API call for one batch.

No Django dependency. Framework-independent.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator

logger = logging.getLogger("services.llm_client")


class EmbeddingError(Exception):
    """Raised when embedding fails after all retries, or for a non-retryable reason."""


class RetryableEmbeddingError(Exception):
    """
    Raised internally by subclasses for transient failures (rate limits,
    timeouts, 5xx errors). Caught by the base class's retry loop; never
    propagates to the caller of embed().
    """


class EmbeddingClient(ABC):
    """Abstract base class for embedding providers."""

    #: Required embedding dimensionality. Validated on every batch.
    EMBEDDING_DIMENSIONS: int = 384 # BAAI/bge-small-en-v1.5 (sentence-transformers): 384 dimensions

    #: Maximum number of texts sent in a single provider API call.
    MAX_BATCH_SIZE: int = 100

    #: Maximum attempts per batch (1 initial + N-1 retries).
    MAX_RETRIES: int = 5

    #: Initial backoff delay in seconds; doubles after each retry.
    INITIAL_BACKOFF_SECONDS: float = 1.0

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed an arbitrary-length list of texts.

        Splits texts into batches of at most MAX_BATCH_SIZE and calls the
        provider once per batch, with retry/backoff applied independently
        per batch. Returns vectors in the same order as the input texts.

        Raises:
            EmbeddingError: if any batch fails after MAX_RETRIES attempts,
                or a provider returns a vector of the wrong dimension.
        """
        if not texts:
            return []

        vectors: list[list[float]] = []
        for batch in self._chunk(texts, self.MAX_BATCH_SIZE):
            batch_vectors = self._embed_batch_with_retry(batch)

            if len(batch_vectors) != len(batch):
                raise EmbeddingError(
                    f"Provider returned {len(batch_vectors)} vectors for a "
                    f"batch of {len(batch)} texts"
                )

            for vector in batch_vectors:
                if len(vector) != self.EMBEDDING_DIMENSIONS:
                    raise EmbeddingError(
                        f"Provider returned a vector of dimension "
                        f"{len(vector)}; expected {self.EMBEDDING_DIMENSIONS}"
                    )

            vectors.extend(batch_vectors)

        return vectors

    @staticmethod
    def _chunk(items: list[str], size: int) -> Iterator[list[str]]:
        for i in range(0, len(items), size):
            yield items[i : i + size]

    def _embed_batch_with_retry(self, batch: list[str]) -> list[list[float]]:
        """Calls _embed_batch() with exponential backoff on transient failures."""
        backoff = self.INITIAL_BACKOFF_SECONDS
        last_exc: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return self._embed_batch(batch)
            except RetryableEmbeddingError as exc:
                last_exc = exc
                if attempt == self.MAX_RETRIES:
                    break
                logger.warning(
                    "embedding_retry attempt=%d/%d backoff=%.1fs error=%s",
                    attempt, self.MAX_RETRIES, backoff, exc,
                )
                time.sleep(backoff)
                backoff *= 2

        raise EmbeddingError(
            f"Embedding failed after {self.MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    @abstractmethod
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        """
        Perform exactly one provider API call for one batch of texts.

        Implementations must raise RetryableEmbeddingError for transient
        failures (rate limits, timeouts, 5xx errors) so the base class's
        retry loop can handle them, and raise EmbeddingError directly for
        non-retryable failures (invalid API key, malformed input, etc.).
        """
        raise NotImplementedError