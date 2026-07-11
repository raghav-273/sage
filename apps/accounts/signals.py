# apps/accounts/signals.py
"""
Automatically creates a UserProfile for every new User.

Connected in AccountsConfig.ready() to avoid AppRegistryNotReady errors.
New users receive no role by default — a role must be explicitly assigned
by an administrator, which triggers an AuditLog entry.

Exception: Django management commands that create superusers
(createsuperuser, data migrations) bypass signals when using
User.objects.create_superuser() with no signal receiver registered yet.
This is handled by the get_or_create pattern in get_or_create_profile().
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance: User, created: bool, **kwargs) -> None:
    if created:
        from apps.accounts.models import UserProfile
        UserProfile.objects.get_or_create(user=instance)