# apps/documents/apps.py

from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """
    Application configuration for the documents app.

    Owns the Document and DocumentPage models.
    Handles document lifecycle: upload → ingestion → status tracking.
    """

    name = "apps.documents"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Documents"