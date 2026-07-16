# apps/accounts/templatetags/account_tags.py
"""
Template tags for RBAC permission checks.

Usage in templates:
    {% load account_tags %}
    {% has_perm request.user "conduct_research" as can_research %}
    {% if can_research %}...{% endif %}
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.simple_tag
def has_perm(user, permission: str) -> bool:
    """Returns True if the user has the named SAGE RBAC permission."""
    if not user or not user.is_authenticated:
        return False
    try:
        return user.profile.has_permission(permission)
    except Exception:
        return False


@register.simple_tag
def pending_registration_count() -> int:
    """Returns count of registrations awaiting admin approval."""
    try:
        from apps.accounts.models import AccountRegistration
        return AccountRegistration.objects.filter(
            status=AccountRegistration.Status.PENDING_APPROVAL
        ).count()
    except Exception:
        return 0