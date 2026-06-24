# apps/portal/rate_limit.py
"""
Per-user rate limiting for the portal's query page, via Django's cache
framework — same mechanism as apps.portal.login_security's failure
tracking, applied to a different problem.

The portal calls services.generation.generation_service.generate_answer()
directly (the established parallel-consumer pattern), bypassing
apps.api.views.QueryView's ScopedRateThrottle entirely. Without an
equivalent limit here, this path alone could exceed Gemini's free-tier
rate limit with nothing stopping it.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

_RATE_LIMIT_CACHE_PREFIX = "portal_query_rate"


def _window_seconds() -> int:
    return getattr(settings, "PORTAL_QUERY_RATE_LIMIT_WINDOW_SECONDS", 60)


def _max_requests() -> int:
    return getattr(settings, "PORTAL_QUERY_RATE_LIMIT_MAX_REQUESTS", 8)


def is_rate_limited(user_id: int) -> bool:
    count = cache.get(f"{_RATE_LIMIT_CACHE_PREFIX}:{user_id}", 0)
    return count >= _max_requests()


def record_request(user_id: int) -> None:
    key = f"{_RATE_LIMIT_CACHE_PREFIX}:{user_id}"
    cache.set(key, cache.get(key, 0) + 1, _window_seconds())