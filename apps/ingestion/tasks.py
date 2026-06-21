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

from celery import shared_task

logger = logging.getLogger("apps.ingestion.tasks")


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