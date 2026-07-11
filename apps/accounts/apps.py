# apps/accounts/apps.py
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """
    Identity, access management, and role-based permissions for SAGE.

    Owns: UserProfile, Role, and AuditLog.
    Does not own authentication views — those live in apps.portal.
    """

    name = "apps.accounts"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Accounts"

    def ready(self) -> None:
        # Ensure UserProfile is created automatically for every new User.
        # Signal import deferred to avoid AppRegistryNotReady errors.
        import apps.accounts.signals  # noqa: F401