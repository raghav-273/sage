# apps/documents/views.py
"""
Views for document upload and status retrieval.

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
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingestion.pipeline import run_ingestion_pipeline

from .models import Document
from .serializers import DocumentDetailSerializer, DocumentUploadSerializer


class DocumentUploadView(APIView):
    """POST /api/documents/"""

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

        try:
            run_ingestion_pipeline(document.id)
        except Exception:
            # run_ingestion_pipeline already persists status=FAILED and
            # error_message on the Document itself. Swallowing here is
            # deliberate: the client gets a normal, parseable 202 response
            # showing the FAILED status and reason, rather than an opaque
            # 500 that would require a separate GET to learn what happened.
            pass

        document.refresh_from_db()
        return Response(
            DocumentDetailSerializer(document).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentDetailView(generics.RetrieveAPIView):
    """
    GET /api/documents/{id}/

    Pure read — no logic beyond the serializer. This is exactly why the
    polling contract above works: this view doesn't know or care whether
    the status it's returning got there synchronously or via a Celery
    worker. Zero changes needed when Milestone 8 lands.
    """

    queryset = Document.objects.all()
    serializer_class = DocumentDetailSerializer
    lookup_field = "id"