# apps/accounts/middleware.py
"""
Intercepts authenticated requests when a forced password reset is pending.

When an administrator sets UserProfile.requires_password_reset=True, the
next request from that user is redirected to the password reset flow
regardless of what URL they were trying to reach.

Exempt URLs: login, logout, password reset, and static/media files.
Without exemptions, the redirect would loop.
"""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


_EXEMPT_URL_PREFIXES = (
    "/login/",
    "/logout/",
    "/password-reset/",
    "/static/",
    "/media/",
)


class RequiresPasswordResetMiddleware:
    def __init__(self, get_response):
        self._get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not any(request.path.startswith(p) for p in _EXEMPT_URL_PREFIXES)
        ):
            try:
                profile = request.user.profile
                if profile.requires_password_reset:
                    return redirect(reverse("password_reset"))
            except Exception:
                pass

        return self._get_response(request)