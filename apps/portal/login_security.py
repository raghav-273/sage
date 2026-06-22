# apps/portal/login_security.py
"""
Lightweight, dependency-free login protection: per-IP failure tracking
via Django's cache framework, and a stateless, signed plain-text
verification challenge — no new package, no new database table.

Failure tracking uses whatever CACHES backend is configured (the default
LocMemCache is correct for this project's single-instance deployment).

The challenge itself never touches the database: the expected answer is
embedded in a cryptographically signed, time-limited token (via
django.core.signing.TimestampSigner) carried in a hidden form field.
Verification is just "unsign and compare" — nothing to expire via a
cron job, nothing to clean up.
"""

from __future__ import annotations

import random

from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

_FAILURE_CACHE_PREFIX = "login_failures"
_SIGNER_SALT = "apps.portal.login_security.challenge"

_signer = TimestampSigner(salt=_SIGNER_SALT)


def _failure_cache_key(ip_address: str) -> str:
    return f"{_FAILURE_CACHE_PREFIX}:{ip_address}"


def _failure_window_seconds() -> int:
    return getattr(settings, "LOGIN_CHALLENGE_WINDOW_SECONDS", 15 * 60)


def _failure_threshold() -> int:
    return getattr(settings, "LOGIN_CHALLENGE_FAILURE_THRESHOLD", 5)


def _token_max_age() -> int:
    return getattr(settings, "LOGIN_CHALLENGE_TOKEN_MAX_AGE", 5 * 60)


def get_client_ip(request) -> str:
    """
    Returns the client's IP address.

    Reads REMOTE_ADDR directly — correct for this project's single-instance
    Docker deployment with no reverse proxy in front of it. If a reverse
    proxy is ever added (deliberately deferred per the architecture), this
    would need to respect X-Forwarded-For instead — flagging that now so
    it isn't a silent gap later.
    """
    return request.META.get("REMOTE_ADDR", "unknown")


def record_failed_attempt(ip_address: str) -> int:
    """Increments and returns the failure count for this IP, within the window."""
    key = _failure_cache_key(ip_address)
    failures = cache.get(key, 0) + 1
    cache.set(key, failures, _failure_window_seconds())
    return failures


def get_failure_count(ip_address: str) -> int:
    return cache.get(_failure_cache_key(ip_address), 0)


def reset_failures(ip_address: str) -> None:
    cache.delete(_failure_cache_key(ip_address))


def challenge_required(ip_address: str) -> bool:
    return get_failure_count(ip_address) >= _failure_threshold()


def generate_challenge() -> tuple[str, str]:
    """
    Returns (question_text, signed_token).

    A simple, non-standard arithmetic question — not adversarially
    hardened against a targeted attacker who studies this exact form,
    but a proportionate deterrent against generic automated login
    scripts, which is the actual threat model for a single-operator
    system. This is a deliberate trade-off, not an oversight.
    """
    a, b = random.randint(2, 9), random.randint(2, 9)
    question = f"What is {a} + {b}?"
    token = _signer.sign(str(a + b))
    return question, token


def verify_challenge(token: str, submitted_answer: str) -> bool:
    """Verifies a submitted answer against a signed challenge token."""
    if not token or not submitted_answer:
        return False
    try:
        expected_answer = _signer.unsign(token, max_age=_token_max_age())
    except (BadSignature, SignatureExpired):
        return False
    return submitted_answer.strip() == expected_answer