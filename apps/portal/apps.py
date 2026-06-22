# apps/portal/apps.py
from django.apps import AppConfig


class PortalConfig(AppConfig):
    """
    HTML template views — the primary demonstration interface. Parallel to
    apps.api (JSON); both call the same service layer independently.
    No models.
    """

    name = "apps.portal"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Portal"