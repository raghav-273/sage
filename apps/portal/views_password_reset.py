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


def _mask_email(email: str) -> str:
    """Returns a****z@domain.com style masked email for display."""
    try:
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked = local[0] + "*" * max(1, len(local) - 1)
        else:
            masked = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{masked}@{domain}"
    except Exception:
        return "your registered email address"


class SagePasswordResetView(DjangoPasswordResetView):
    template_name = "portal/password_reset.html"
    email_template_name = "emails/password_reset.txt"
    html_email_template_name = "emails/password_reset.html"
    subject_template_name = "emails/password_reset_subject.txt"

    def get_initial(self):
        """Pre-fill email if user is already authenticated."""
        initial = super().get_initial()
        if self.request.user.is_authenticated and self.request.user.email:
            initial["email"] = self.request.user.email
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated and self.request.user.email:
            context["prefilled_email"] = self.request.user.email
            context["masked_email"] = _mask_email(self.request.user.email)
        return context

    def form_valid(self, form):
        email = form.cleaned_data.get("email", "")
        from django.contrib.auth import get_user_model
        User = get_user_model()
        for user in User.objects.filter(email__iexact=email, is_active=True):
            log_password_reset_requested(self.request, user)
        return super().form_valid(form)


class SagePasswordResetDoneView(DjangoPasswordResetDoneView):
    template_name = "portal/password_reset_done.html"


class SagePasswordResetConfirmView(DjangoPasswordResetConfirmView):
    template_name = "portal/password_reset_confirm.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.user
        log_password_reset_completed(self.request, user)
        if user.email:
            send_password_reset_complete_email(recipient=user.email, username=user.username)
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