# apps/ingestion/tasks.py
"""
Celery task wrapping the existing ingestion pipeline.

Zero ingestion logic lives here — this file exists purely to make
apps.ingestion.pipeline.run_ingestion_pipeline callable asynchronously.
Automatically discovered by Celery via app.autodiscover_tasks() in
config/celery.py (apps.ingestion is already in INSTALLED_APPS) — no
additional registration needed.
"""

from __future__ import annotations

import logging
import uuid

from celery import shared_task

logger = logging.getLogger("apps.ingestion.tasks")


MAX_CAPTION_RETRIES = 5
# Base backoff for 429 errors: 2 minutes, doubling each retry.
# Gemini free-tier quota resets per minute and per day — minute-scale
# backoff is appropriate for transient exhaustion. Day-scale exhaustion
# will exhaust retries, leaving caption_status=FAILED; the document
# remains READY and fully functional without captions.
CAPTION_BACKOFF_BASE_SECONDS = 120



@shared_task(name="apps.ingestion.run_ingestion_pipeline_task")
def run_ingestion_pipeline_task(document_id: str) -> None:
    """
    Celery entry point for asynchronous ingestion.

    document_id is a string, not a uuid.UUID instance: Celery's JSON task
    serializer (configured via CELERY_TASK_SERIALIZER) cannot serialize
    UUID objects directly, so the caller must pass str(document.id).
    Every downstream call (Document.objects.get(id=...), etc.) already
    accepts a string for a UUID PK lookup without any change.

    No retry policy is configured here, deliberately: run_ingestion_pipeline
    is fully idempotent — re-running it after a failure safely re-extracts,
    re-chunks, and re-embeds (chunk_document already deletes and recreates
    chunks; embedding generation only touches chunks with NULL embeddings).
    A manual re-invocation of this task is always a safe, sufficient
    recovery path. Automatic retries would also retry genuinely permanent
    failures (a missing or corrupt PDF), adding delay and noisy status
    flapping for no benefit. Add retries later if real-world transient
    failures turn out to justify it — this is a one-line addition.
    """
    logger.info("ingestion_task_started document_id=%s", document_id)
    from apps.ingestion.pipeline import run_ingestion_pipeline

    run_ingestion_pipeline(document_id)
    logger.info("ingestion_task_completed document_id=%s", document_id)
    
@shared_task(
    name="apps.ingestion.generate_figure_captions_task",
    bind=True,
    max_retries=MAX_CAPTION_RETRIES,
)
def generate_figure_captions_task(self, document_id: str) -> None:
    """
    Generates captions for all DiagramAssets in a document.

    Runs after the document reaches READY. Failures do not affect
    document status — the document remains fully queryable.

    Retry policy:
        - 429 (quota exhausted): exponential backoff, retried up to
          MAX_CAPTION_RETRIES times
        - 404 (model not found): NOT retried — configuration error
        - 503 (unavailable): retried with short backoff
        - All others: logged, caption_status=FAILED, no retry
    """
    from apps.chunks.models import ContentChunk, DiagramAsset
    from apps.documents.models import Document
    from services.generation.image_captioner import (
        CaptionError,
        QuotaExhaustedError,
        generate_caption,
    )
    from django.conf import settings
    from pathlib import Path

    logger.info("caption_task_started document_id=%s", document_id)

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("caption_task_document_not_found document_id=%s", document_id)
        return

    diagrams = DiagramAsset.objects.filter(
        document=document,
        caption_status__in=[
            DiagramAsset.CaptionStatus.PENDING,
            DiagramAsset.CaptionStatus.FAILED,
        ],
    ).order_by("id")

    if not diagrams.exists():
        logger.info(
            "caption_task_no_pending document_id=%s", document_id
        )
        return

    for diagram in diagrams:
        diagram.caption_status = DiagramAsset.CaptionStatus.IN_PROGRESS
        diagram.caption_attempts += 1
        diagram.save(update_fields=["caption_status", "caption_attempts"])

        image_path = Path(settings.MEDIA_ROOT) / diagram.image_path

        try:
            caption_text = generate_caption(image_path)
        except QuotaExhaustedError as exc:
            # 429 — back off and retry the whole task
            diagram.caption_status = DiagramAsset.CaptionStatus.PENDING
            diagram.caption_error = str(exc)
            diagram.save(update_fields=["caption_status", "caption_error"])

            retry_in = CAPTION_BACKOFF_BASE_SECONDS * (2 ** self.request_stack[0].retries)
            logger.warning(
                "caption_quota_exhausted document_id=%s diagram_id=%s "
                "retrying_in=%ds",
                document_id, diagram.id, retry_in,
            )
            raise self.retry(exc=exc, countdown=retry_in)

        except CaptionError as exc:
            # Non-retryable error (model not found, auth failure, etc.)
            diagram.caption_status = DiagramAsset.CaptionStatus.FAILED
            diagram.caption_error = str(exc)
            diagram.save(update_fields=["caption_status", "caption_error"])
            logger.error(
                "caption_permanent_failure document_id=%s diagram_id=%s error=%s",
                document_id, diagram.id, exc,
            )
            continue

        except Exception as exc:
            diagram.caption_status = DiagramAsset.CaptionStatus.FAILED
            diagram.caption_error = str(exc)
            diagram.save(update_fields=["caption_status", "caption_error"])
            logger.error(
                "caption_unexpected_error document_id=%s diagram_id=%s error=%s",
                document_id, diagram.id, exc,
            )
            continue

        if caption_text is None:
            diagram.caption_status = DiagramAsset.CaptionStatus.SKIPPED
            diagram.save(update_fields=["caption_status"])
        else:
            diagram.caption = caption_text
            diagram.caption_status = DiagramAsset.CaptionStatus.COMPLETE
            diagram.caption_error = ""
            diagram.save(update_fields=["caption", "caption_status", "caption_error"])

            # Create a CAPTION ContentChunk so this figure is retrievable
            # through the standard retrieval pipeline.
            existing_page = diagram.page
            max_index = (
                ContentChunk.objects
                .filter(document=document)
                .order_by("-chunk_index")
                .values_list("chunk_index", flat=True)
                .first()
            )
            next_index = (max_index + 1) if max_index is not None else 0

            ContentChunk.objects.update_or_create(
                document=document,
                diagram_asset=diagram,
                chunk_type=ContentChunk.ChunkType.CAPTION,
                defaults={
                    "page": existing_page,
                    "chunk_index": next_index,
                    "chunk_text": caption_text,
                    "section_identifier": None,
                    "token_count": 0,
                },
            )

            logger.info(
                "caption_generated document_id=%s diagram_id=%s chars=%d",
                document_id, diagram.id, len(caption_text),
            )

    logger.info("caption_task_completed document_id=%s", document_id)