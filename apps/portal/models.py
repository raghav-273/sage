# apps/portal/models.py
"""
LoginAttempt — persisted audit record for every login event.

Stored as structured data, not just log lines, so an operator can
query, filter, and review the login history without grepping log files.
username_attempted is stored as a plain string (not a FK to User)
because failed attempts may reference usernames that don't exist.
"""

from __future__ import annotations

from django.db import models


class LoginAttempt(models.Model):

    class FailureReason(models.TextChoices):
        BAD_CREDENTIALS = "bad_credentials", "Bad credentials"
        TURNSTILE_REJECTED = "turnstile_rejected", "Turnstile rejected"
        TURNSTILE_ABSENT = "turnstile_absent", "Turnstile token absent"
        FALLBACK_FAILED = "fallback_failed", "Fallback challenge failed"
        HONEYPOT = "honeypot", "Honeypot triggered"
        LOCKED_OUT = "locked_out", "IP locked out"

    ip_address = models.GenericIPAddressField()
    username_attempted = models.CharField(max_length=255, blank=True, default="")
    success = models.BooleanField()
    failure_reason = models.CharField(
        max_length=30,
        choices=FailureReason.choices,
        blank=True,
        default="",
    )
    user_agent = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["ip_address", "timestamp"], name="loginattempt_ip_ts_idx"),
            models.Index(fields=["timestamp"], name="loginattempt_ts_idx"),
        ]

    def __str__(self) -> str:
        outcome = "SUCCESS" if self.success else f"FAIL({self.failure_reason})"
        return f"{self.ip_address} — {self.username_attempted} — {outcome} — {self.timestamp:%Y-%m-%d %H:%M}"