# services/generation/image_captioner.py
"""
Generates technical captions for engineering diagrams via Gemini's vision API.

Exceptions are now typed so the caption task can distinguish between:
    QuotaExhaustedError (429) — retryable with backoff
    CaptionError           — non-retryable (model not found, auth, etc.)
    None return            — image has no useful content (NO_CAPTION)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from google import genai
from google.genai import errors, types

logger = logging.getLogger("services.generation.image_captioner")

CAPTION_SYSTEM_PROMPT = (
    "You are analyzing an engineering diagram or technical figure extracted from a "
    "railway standards document. Generate a concise, factual caption (2-4 sentences) "
    "that describes what the diagram shows; names key components, labels, or section "
    "identifiers visible in the image; notes any measurements, tolerances, or "
    "specifications visible; and identifies the diagram type. "
    "If the image is too small, completely blank, or decorative (logo, divider, bullet), "
    "respond with exactly the single word: NO_CAPTION"
)


class CaptionError(Exception):
    """Non-retryable caption generation failure."""


class QuotaExhaustedError(CaptionError):
    """429 quota exhaustion — retryable with backoff."""


def generate_caption(
    image_path: Path,
    mime_type: str = "image/jpeg",
    api_key: str | None = None,
    model: str | None = None,
) -> str | None:
    """
    Returns a caption string, or None for blank/decorative images.

    Raises:
        QuotaExhaustedError: on HTTP 429 — caller should retry with backoff
        CaptionError: on any other non-retryable failure
    """
    if not image_path.exists():
        logger.warning("image_caption_skipped reason=file_not_found path=%s", image_path)
        return None

    if image_path.stat().st_size == 0:
        logger.warning("image_caption_skipped reason=empty_file path=%s", image_path)
        return None

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_key:
        raise CaptionError("GEMINI_API_KEY is not configured")

    resolved_model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        raise CaptionError(f"Cannot read image file: {exc}") from exc

    try:
        client = genai.Client(api_key=resolved_key)
        response = client.models.generate_content(
            model=resolved_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                CAPTION_SYSTEM_PROMPT,
            ],
        )
    except errors.APIError as exc:
        if exc.code == 429:
            raise QuotaExhaustedError(f"Quota exhausted: {exc}") from exc
        raise CaptionError(f"Gemini API error {exc.code}: {exc}") from exc
    except Exception as exc:
        raise CaptionError(f"Unexpected Gemini client error: {exc}") from exc

    if not response.text:
        return None

    caption = response.text.strip()
    if not caption or caption == "NO_CAPTION":
        logger.debug("image_caption_no_content path=%s", image_path)
        return None

    logger.info("image_caption_generated path=%s chars=%d", image_path, len(caption))
    return caption