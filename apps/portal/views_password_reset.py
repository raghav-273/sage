# apps/portal/views_password_reset.py
"""
Password reset views — thin wrappers over Django's built-in auth views.

Django's PasswordResetView, PasswordResetConfirmView, PasswordResetDoneView,
and PasswordResetCompleteView already implement HMAC-signed, expiring,
single-use tokens correctly. These subclasses override only:
    - template_name (to use SAGE templates)
    - form_valid / form_invalid hooks (to write audit log entries and
      send the SAGE-branded notification email on completion)

No custom token generation or validation is implemented here — Django's
well-audited PasswordResetTokenGenerator handles that.
"""

from __future__ import annotations

import logging

from django.contrib.auth.views import (
    PasswordResetCompleteView as DjangoPasswordResetCompleteView,
)
from django.contrib.auth.views import (
    PasswordResetConfirmView as DjangoPasswordResetConfirmView,
)
from django.contrib.auth.views import PasswordResetDoneView as DjangoPasswordResetDoneView
from django.contrib.auth.views import PasswordResetView as DjangoPasswordResetView

from services.audit.audit_service import (
    log_password_reset_completed,
    log_password_reset_requested,
)
from services.email.mail_service import (
    send_password_reset_complete_email,
)

logger = logging.getLogger("apps.portal.password_reset")


class SagePasswordResetView(DjangoPasswordResetView):
    """
    POST /password-reset/

    Overrides the default email sending with SAGE-branded templates via
    mail_service.send_email(). Inherits Django's token generation and
    rate-implicit protection (the view always returns HTTP 200 regardless
    of whether an email address exists — enumeration prevention built in).
    """

    template_name = "portal/password_reset.html"
    email_template_name = "emails/password_reset.txt"
    html_email_template_name = "emails/password_reset.html"
    subject_template_name = "emails/password_reset_subject.txt"

    def form_valid(self, form):
        """Write audit log for every reset request, then defer to Django."""
        email = form.cleaned_data.get("email", "")
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users = list(User.objects.filter(email__iexact=email, is_active=True))
        for user in users:
            log_password_reset_requested(self.request, user)

        logger.info(
            "password_reset_requested email=%r user_count=%d",
            email, len(users),
        )
        return super().form_valid(form)


class SagePasswordResetDoneView(DjangoPasswordResetDoneView):
    template_name = "portal/password_reset_done.html"


class SagePasswordResetConfirmView(DjangoPasswordResetConfirmView):
    """
    POST /password-reset/<uidb64>/<token>/

    Handles token validation (inherited) and triggers the completion
    notification email and audit log write on success.
    """

    template_name = "portal/password_reset_confirm.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        # At this point Django has already saved the new password and
        # invalidated the token. request.user is still the user from the
        # token, accessible via the view's user attribute.
        user = self.user
        log_password_reset_completed(self.request, user)

        if user.email:
            sent = send_password_reset_complete_email(
                recipient=user.email,
                username=user.username,
            )
            if not sent:
                logger.warning(
                    "password_reset_completion_email_failed user=%s",
                    user.username,
                )

        # If a forced password reset was pending, clear the flag.
        try:
            profile = user.profile
            if profile.requires_password_reset:
                profile.requires_password_reset = False
                profile.save(update_fields=["requires_password_reset"])
        except Exception:
            pass

        return response


class SagePasswordResetCompleteView(DjangoPasswordResetCompleteView):
    template_name = "portal/password_reset_complete.html"