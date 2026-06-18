# apps/ingestion/apps.py

from django.apps import AppConfig


class IngestionConfig(AppConfig):
    """
    Application configuration for the ingestion app.

    Owns Celery tasks (tasks.py) and pipeline orchestration (pipeline.py).
    Has no database models. Coordinates the extraction and chunking pipeline
    by reading from apps.documents and writing to apps.chunks.
    """

    name = "apps.ingestion"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Ingestion"