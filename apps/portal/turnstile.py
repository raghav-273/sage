# apps/portal/turnstile.py
"""
Cloudflare Turnstile server-side verification.

Chosen over Google reCAPTCHA for this project specifically: no Google
account dependency, a minimal non-puzzle widget (fits the "no AI-clutter,
professional government portal" design brief far better than reCAPTCHA's
image grids), and official dummy sitekeys that work on localhost without
requiring a Cloudflare account first.

verify_turnstile() returns True/False for a definitive Cloudflare
response, or None specifically when Cloudflare's API itself could not
be reached — distinct from "rejected". apps.portal.views.PortalLoginView
uses this distinction to degrade to the existing plain-text fallback
challenge (apps.portal.login_security) rather than locking the operator
out during a Cloudflare-side outage.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("apps.portal.turnstile")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SITEVERIFY_TIMEOUT_SECONDS = 5


def verify_turnstile(token: str, remote_ip: str) -> bool | None:
    """
    Returns True if Cloudflare confirms the token, False if Cloudflare
    explicitly rejects it, or None if verification could not be
    completed at all (network error, timeout, malformed response,
    missing secret key) — never treated as a silent pass.
    """
    if not token:
        return False  # caller handles "no token" as a distinct, accessible-fallback case

    secret_key = settings.TURNSTILE_SECRET_KEY
    if not secret_key:
        logger.error("turnstile_verify_skipped reason=no_secret_key_configured")
        return None

    payload = urllib.parse.urlencode(
        {"secret": secret_key, "response": token, "remoteip": remote_ip}
    ).encode("utf-8")

    try:
        request = urllib.request.Request(SITEVERIFY_URL, data=payload, method="POST")
        with urllib.request.urlopen(request, timeout=SITEVERIFY_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("turnstile_verify_unreachable error=%s", exc)
        return None

    success = bool(result.get("success", False))
    if not success:
        logger.info("turnstile_verify_rejected error_codes=%s", result.get("error-codes"))
    return success