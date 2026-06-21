# apps/documents/views.py
"""
Views for document upload and status retrieval.
#OLD LOGIC:
DocumentUploadView orchestrates: validate -> write file -> create
Document -> run ingestion. The actual ingestion logic lives entirely in
apps.ingestion.pipeline.run_ingestion_pipeline — already built, untouched.

Ingestion runs synchronously here because no Celery task exists yet
(Milestone 8). Returning 202 Accepted (not 201 Created) is deliberate: it
keeps the response *contract* stable across that migration. Today, 202
means "already processed, here's the final status" only because the call
happens to be synchronous; once Milestone 8 wraps this in a Celery task,
202 will mean what it normally means — "accepted, still processing" —
and the client-facing behavior (poll GET /api/documents/{id}/) doesn't
change at all. Clients that already poll status, as they should given a
202 response, need zero changes when this becomes async.

#NEW LOGIC:

Views for document upload and status retrieval.

DocumentUploadView orchestrates: validate -> write file -> create
Document -> enqueue ingestion. As of this change, ingestion runs
asynchronously via Celery (apps.ingestion.tasks.run_ingestion_pipeline_task)
— the view returns as soon as the task is enqueued, without waiting for
extraction, chunking, or embedding to complete.

"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingestion.tasks import run_ingestion_pipeline_task

from .models import Document
from .serializers import DocumentDetailSerializer, DocumentUploadSerializer


class DocumentUploadView(APIView):
    """
    POST /api/documents/

    Returns 202 Accepted immediately after enqueueing ingestion — the
    response reflects status=QUEUED, not a final outcome. Clients poll
    GET /api/documents/{id}/ to observe QUEUED -> EXTRACTING -> CHUNKING
    -> EMBEDDING -> READY (or FAILED) as the worker processes the task.
    """

    def post(self, request, *args, **kwargs) -> Response:
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        name = serializer.validated_data.get("name") or uploaded_file.name

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

        return Response(
            DocumentDetailSerializer(document).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentDetailView(generics.RetrieveAPIView):
    """
    GET /api/documents/{id}/

    Unchanged. Pure read — it never knew or cared whether ingestion ran
    synchronously or asynchronously, which is exactly why no changes are
    needed here.
    """

    queryset = Document.objects.all()
    serializer_class = DocumentDetailSerializer
    lookup_field = "id"