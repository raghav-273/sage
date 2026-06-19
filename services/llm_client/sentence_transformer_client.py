# services/llm_client/sentence_transformer_client.py
"""
Local embedding client using sentence-transformers — no API, no network
call at inference time, no cost. Runs entirely on the machine running the
Django/Celery process.

Model: BAAI/bge-small-en-v1.5 (384-dimensional, native — no truncation or
forced output_dimensionality needed, unlike the now-retired Gemini
embedding path which had to force output_dimensionality=1536 to match
OpenAI).

Known limitation: BAAI's bge-* model family recommends prefixing QUERY
text (not document/passage text) with an instruction string for best
retrieval performance:
    "Represent this sentence for searching relevant passages: "
The EmbeddingClient.embed() interface is symmetric — it does not
distinguish query embedding calls from document embedding calls — so
this implementation does not apply that prefix, to preserve the existing
abstraction exactly as specified. If retrieval quality needs improvement
later, consider adding an embed_query() method to the base class that
defaults to embed() but allows providers to override it.
"""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

from .base import EmbeddingClient, EmbeddingError


class SentenceTransformerEmbeddingClient(EmbeddingClient):
    """Local embedding client using sentence-transformers."""

    EMBEDDING_DIMENSIONS = 384
    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

    # Local inference has no rate limit to respect; this only controls how
    # many texts are passed to model.encode() per call.
    MAX_BATCH_SIZE = 64

    # Local inference failures (OOM, corrupt model state) are not
    # transient — a single attempt with no retry/backoff is correct.
    MAX_RETRIES = 1

    def __init__(self, model_name: str | None = None, device: str | None = None) -> None:
        """
        Args:
            model_name: HuggingFace model identifier. Defaults to
                BAAI/bge-small-en-v1.5.
            device: "cpu" or "cuda". Defaults to sentence-transformers'
                auto-detection — CPU on a machine with no GPU, which is
                the expected environment for this project (Apple Silicon
                Docker container, no GPU passthrough).
        """
        try:
            self._model = SentenceTransformer(
                model_name or self.DEFAULT_MODEL,
                device=device,
            )
        except Exception as exc:
            raise EmbeddingError(
                f"Failed to load sentence-transformers model "
                f"'{model_name or self.DEFAULT_MODEL}': {exc}"
            ) from exc

        actual_dim = self._model.get_sentence_embedding_dimension()
        if actual_dim != self.EMBEDDING_DIMENSIONS:
            raise EmbeddingError(
                f"Loaded model produces {actual_dim}-dimensional vectors; "
                f"expected {self.EMBEDDING_DIMENSIONS}. Check model_name."
            )

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        try:
            vectors = self._model.encode(
                batch,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            # Not transient — raise directly rather than via
            # RetryableEmbeddingError, since retrying won't help.
            raise EmbeddingError(f"Local embedding inference failed: {exc}") from exc

        return [vector.tolist() for vector in vectors]