# apps/api/apps.py
from django.apps import AppConfig


class ApiConfig(AppConfig):
    """
    Cross-cutting DRF views that don't belong to a specific model-owning
    app — currently just the question-answering endpoint. No models.
    """

    name = "apps.api"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "API"