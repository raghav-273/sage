# services/generation/image_captioner.py
"""
Generates technical captions for engineering diagrams via Gemini's vision API.

Non-fatal by design: generate_caption() returns None on any failure —
unreadable image, API error, transient 503, deliberate NO_CAPTION
response for decorative content — and never raises. The ingestion
pipeline continues without that caption; the DiagramAsset remains
captionless rather than failing the entire document.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger("services.generation.image_captioner")

CAPTION_SYSTEM_PROMPT = (
    "You are analyzing an engineering diagram or technical figure extracted from a "
    "railway standards document. Generate a concise, factual caption (2–4 sentences) "
    "that: describes what the diagram shows; names key components, labels, or section "
    "identifiers visible in the image; notes any measurements, tolerances, or "
    "specifications visible; and identifies the diagram type (schematic, cross-section, "
    "flowchart, table, detail view, etc.). "
    "If the image is too small, completely blank, decorative (logo, divider, bullet), "
    "or contains no useful technical content, respond with exactly the single word: "
    "NO_CAPTION"
)


def generate_caption(
    image_path: Path,
    mime_type: str = "image/png",
    api_key: str | None = None,
    model: str | None = None,
) -> str | None:
    """
    Returns a technical caption string, or None on any failure.

    Args:
        image_path: absolute path to the image file on disk.
        mime_type: MIME type of the image (e.g. "image/png", "image/jpeg").
        api_key: overrides GEMINI_API_KEY env var when set.
        model: overrides GEMINI_MODEL env var when set.
    """
    if not image_path.exists():
        logger.warning("image_caption_skipped reason=file_not_found path=%s", image_path)
        return None

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_key:
        logger.warning("image_caption_skipped reason=no_api_key path=%s", image_path)
        return None

    resolved_model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        logger.warning("image_caption_skipped reason=read_error path=%s error=%s", image_path, exc)
        return None

    if len(image_bytes) == 0:
        logger.warning("image_caption_skipped reason=empty_file path=%s", image_path)
        return None

    try:
        client = genai.Client(api_key=resolved_key)
        response = client.models.generate_content(
            model=resolved_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                CAPTION_SYSTEM_PROMPT,
            ],
        )
    except Exception as exc:
        logger.warning("image_caption_failed path=%s error=%s", image_path, exc)
        return None

    if not response.text:
        return None

    caption = response.text.strip()
    if not caption or caption == "NO_CAPTION":
        logger.debug("image_caption_no_content path=%s", image_path)
        return None

    logger.info("image_caption_generated path=%s chars=%d", image_path, len(caption))
    return caption