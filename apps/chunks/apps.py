# apps/chunks/apps.py

from django.apps import AppConfig


class ChunksConfig(AppConfig):
    """
    Application configuration for the chunks app.

    Owns ContentChunk (text segments with embeddings) and
    DiagramAsset (extracted images with metadata).
    These are the primary retrieval units produced by the ingestion pipeline.
    """

    name = "apps.chunks"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Chunks"