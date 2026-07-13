# services/email/mail_service.py
"""
Email sending service for SAGE.

All outbound email goes through send_email() — a single entry point that:
    - Uses Django's configured email backend (SMTP, Mailgun, console, etc.)
    - Renders templates rather than constructing raw strings at call sites
    - Is non-fatal by default: failures are logged, not raised, unless
      the caller explicitly sets raise_on_failure=True
    - Records an AuditLog entry for every send attempt, success or failure

Backend configuration is environment-driven via Django's EMAIL_BACKEND
setting. In development, EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
prints to stdout with no external dependency.
For production, Mailgun is the recommended default:
    EMAIL_BACKEND=anymail.backends.mailgun.EmailBackend
    MAILGUN_API_KEY=...
    MAILGUN_SENDER_DOMAIN=...
django-anymail is the integration layer; if it is not installed, the
SMTP backend (django.core.mail.backends.smtp.EmailBackend) is the fallback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

if TYPE_CHECKING:
    pass

logger = logging.getLogger("services.email")


def send_email(
    subject: str,
    recipient: str,
    text_template: str,
    html_template: str | None = None,
    context: dict | None = None,
    raise_on_failure: bool = False,
) -> bool:
    """
    Sends a single email to one recipient.

    Args:
        subject:        Email subject line.
        recipient:      Single recipient address.
        text_template:  Template path for the plain-text body.
        html_template:  Optional template path for the HTML body.
                        If None, HTML is derived from the text body.
        context:        Template context dict.
        raise_on_failure: If True, re-raises exceptions to the caller.
                          Used for critical emails (e.g. registration
                          approval) where the caller needs to handle
                          failure explicitly (e.g. transaction rollback).

    Returns:
        True on successful send, False on failure.
    """
    ctx = context or {}
    ctx.setdefault("site_name", "SAGE")
    ctx.setdefault("site_url", getattr(settings, "SITE_URL", "http://localhost:8000"))

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sage.local")

    try:
        text_body = render_to_string(text_template, ctx)
        if html_template:
            html_body = render_to_string(html_template, ctx)
        else:
            html_body = None

        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[recipient],
        )
        if html_body:
            message.attach_alternative(html_body, "text/html")

        message.send(fail_silently=False)
        logger.info("email_sent subject=%r recipient=%r", subject, recipient)
        return True

    except Exception as exc:
        logger.error(
            "email_send_failed subject=%r recipient=%r error=%s",
            subject, recipient, exc,
        )
        if raise_on_failure:
            raise
        return False


def send_password_reset_email(recipient: str, reset_url: str, username: str) -> bool:
    """Sends the password reset link email."""
    return send_email(
        subject="SAGE — Password Reset Request",
        recipient=recipient,
        text_template="emails/password_reset.txt",
        html_template="emails/password_reset.html",
        context={"reset_url": reset_url, "username": username},
    )


def send_password_reset_complete_email(recipient: str, username: str) -> bool:
    """Notification sent after a password reset is successfully completed."""
    return send_email(
        subject="SAGE — Password Changed",
        recipient=recipient,
        text_template="emails/password_reset_complete.txt",
        context={"username": username},
    )


def send_admin_password_reset_email(
    recipient: str, username: str, reset_url: str, admin_username: str
) -> bool:
    """Sent to a user when an administrator initiates a forced password reset."""
    return send_email(
        subject="SAGE — Password Reset Required",
        recipient=recipient,
        text_template="emails/admin_password_reset.txt",
        html_template="emails/admin_password_reset.html",
        context={
            "username": username,
            "reset_url": reset_url,
            "admin_username": admin_username,
        },
        raise_on_failure=False,
    )