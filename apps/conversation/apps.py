# apps/conversation/apps.py
from django.apps import AppConfig


class ConversationConfig(AppConfig):
    """
    Document-scoped conversation sessions. Owns DocumentSession and
    ConversationTurn. Sits above services.generation, parallel to how
    apps.ingestion.pipeline sits above services.extractors/chunkers.
    """

    name = "apps.conversation"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Conversation"