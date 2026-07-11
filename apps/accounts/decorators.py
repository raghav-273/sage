# apps/accounts/decorators.py
"""
Permission-aware view decorators for SAGE RBAC.

requires_permission() is the primary decorator. It checks the RBAC
permission system rather than Django's built-in content-type permissions.
Stack with @login_required when you want authentication enforced separately,
or rely on requires_permission() alone (it enforces authentication too).
"""

from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def requires_permission(permission: str):
    """
    View decorator that enforces a single SAGE RBAC permission.

    Unauthenticated requests are redirected to LOGIN_URL, not given a
    403 — consistent with Django's @login_required convention.

    Authenticated requests without the required permission raise
    PermissionDenied (HTTP 403), rendered by Django's standard 403 handler.

    Usage:
        @requires_permission(Permission.UPLOAD_DOCUMENTS)
        def document_upload_page(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"{settings.LOGIN_URL}?next={request.path}")

            try:
                profile = request.user.profile
            except Exception:
                # Profile missing — treat as read_only (no sensitive permissions).
                # This can happen for users created before the accounts app existed.
                from apps.accounts.models import UserProfile
                profile, _ = UserProfile.objects.get_or_create(user=request.user)

            if not profile.has_permission(permission):
                raise PermissionDenied(
                    f"Your account does not have the '{permission}' permission."
                )

            return view_func(request, *args, **kwargs)

        return _wrapped_view
    return decorator