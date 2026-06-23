# apps/documents/services.py
"""
Document creation service: persists an uploaded file to disk, creates
the Document record, and enqueues ingestion.

Extracted from DocumentUploadView in Milestone 10 once a second caller
(apps.portal.views.document_upload_page) needed identical logic — shared
here rather than duplicated across the JSON API view and the HTML portal
view.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from apps.ingestion.tasks import run_ingestion_pipeline_task

from .models import Document


def create_document_and_enqueue(uploaded_file: UploadedFile, name: str) -> Document:
    """
    Writes uploaded_file to MEDIA_ROOT, creates a Document record with
    status=QUEUED, and enqueues the ingestion Celery task.

    Caller is responsible for validating uploaded_file beforehand (file
    type, size) — this function assumes a valid PDF and performs no
    validation itself.
    """
    relative_path = Path(settings.DOCUMENTS_UPLOAD_DIR) / f"{uuid.uuid4()}.pdf"
    absolute_path = Path(settings.MEDIA_ROOT) / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)

    with absolute_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    document = Document.objects.create(
        name=name,
        original_filename=uploaded_file.name,
        file_path=str(relative_path),
        file_size_bytes=absolute_path.stat().st_size,
        mime_type=uploaded_file.content_type or "application/pdf",
    )

    document.status = Document.Status.QUEUED
    document.save(update_fields=["status"])
    run_ingestion_pipeline_task.delay(str(document.id))

    return document