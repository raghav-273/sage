# apps/portal/login_security.py
"""
Login protection: per-IP failure tracking, adaptive Turnstile challenge,
temporary IP lockout, and honeypot detection.

All state lives in Django's cache (backed by Redis in production —
required for correctness when running multiple gunicorn workers).
"""

from __future__ import annotations

import logging
import random
import time

from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

logger = logging.getLogger("apps.portal.login_security")

_FAILURE_CACHE_PREFIX = "login_failures"
_LOCKOUT_CACHE_PREFIX = "login_lockout"
_SIGNER_SALT = "apps.portal.login_security.challenge"
_VERIFICATION_WORDS = ["SAGE", "RAILWAY", "VERIFY", "SECURE", "ENGINE", "STANDARD"]

_signer = TimestampSigner(salt=_SIGNER_SALT)


# ── Configuration helpers ────────────────────────────────────────────

def _failure_window_seconds() -> int:
    return getattr(settings, "LOGIN_CHALLENGE_WINDOW_SECONDS", 15 * 60)


def _failure_threshold() -> int:
    return getattr(settings, "LOGIN_CHALLENGE_FAILURE_THRESHOLD", 0)


def _token_max_age() -> int:
    return getattr(settings, "LOGIN_CHALLENGE_TOKEN_MAX_AGE", 5 * 60)


def _lockout_threshold() -> int:
    return getattr(settings, "LOGIN_LOCKOUT_THRESHOLD", 10)


def _lockout_duration_seconds() -> int:
    return getattr(settings, "LOGIN_LOCKOUT_DURATION_SECONDS", 15 * 60)


# ── IP helpers ───────────────────────────────────────────────────────

def get_client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "unknown")


# ── Failure tracking ─────────────────────────────────────────────────

def _failure_cache_key(ip: str) -> str:
    return f"{_FAILURE_CACHE_PREFIX}:{ip}"


def get_failure_count(ip: str) -> int:
    return cache.get(_failure_cache_key(ip), 0)


def record_failed_attempt(ip: str) -> int:
    """Increments failure count. Returns the new total."""
    key = _failure_cache_key(ip)
    count = cache.get(key, 0) + 1
    cache.set(key, count, _failure_window_seconds())

    # Trigger a lockout once the harder threshold is crossed.
    if count >= _lockout_threshold():
        _set_lockout(ip)

    return count


def reset_failures(ip: str) -> None:
    cache.delete(_failure_cache_key(ip))
    cache.delete(_lockout_cache_key(ip))


# ── Lockout ──────────────────────────────────────────────────────────

def _lockout_cache_key(ip: str) -> str:
    return f"{_LOCKOUT_CACHE_PREFIX}:{ip}"


def _set_lockout(ip: str) -> None:
    duration = _lockout_duration_seconds()
    expiry_at = time.time() + duration
    cache.set(_lockout_cache_key(ip), True, duration)
    # Store expiry timestamp separately — Django's native RedisCache has
    # no .ttl() method; computing remaining time from a stored timestamp
    # works on any cache backend without extra dependencies.
    cache.set(f"{_lockout_cache_key(ip)}:expiry", expiry_at, duration)
    logger.warning("login_lockout_set ip=%s duration_seconds=%d", ip, duration)


def lockout_remaining_seconds(ip: str) -> int:
    """Returns approximate remaining lockout seconds. 0 if not locked out."""
    expiry_at = cache.get(f"{_lockout_cache_key(ip)}:expiry")
    if expiry_at is None:
        return 0
    return max(0, int(expiry_at - time.time()))

def is_locked_out(ip: str) -> bool:
    return bool(cache.get(_lockout_cache_key(ip)))



# ── Challenge threshold ──────────────────────────────────────────────

def challenge_required(ip: str) -> bool:
    """True when Turnstile/fallback challenge is needed (always true at threshold=0)."""
    return get_failure_count(ip) >= _failure_threshold()


# ── Fallback plain-text challenge ────────────────────────────────────

def generate_challenge() -> tuple[str, str]:
    """Returns (question_text, signed_token). Randomised between two types."""
    challenge_type = random.choice(("arithmetic", "word"))
    if challenge_type == "arithmetic":
        a, b = random.randint(2, 9), random.randint(2, 9)
        question = f"What is {a} + {b}?"
        answer = str(a + b)
    else:
        word = random.choice(_VERIFICATION_WORDS)
        question = f'Type the following word exactly: "{word}"'
        answer = word
    return question, _signer.sign(answer)


def verify_challenge(token: str, submitted: str) -> bool:
    if not token or not submitted:
        return False
    try:
        expected = _signer.unsign(token, max_age=_token_max_age())
    except (BadSignature, SignatureExpired):
        return False
    return submitted.strip().lower() == expected.strip().lower()


# ── Honeypot ─────────────────────────────────────────────────────────

def honeypot_triggered(request) -> bool:
    """
    Returns True if the hidden honeypot field was filled in.
    Bots commonly fill every visible text field; humans never see this one.
    """
    return bool(request.POST.get("contact_url", "").strip())