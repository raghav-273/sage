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

# UPDATED LOGIC:

Views for document upload and status retrieval.

DocumentUploadView orchestrates: validate -> write file -> create
Document -> enqueue ingestion. As of this change, ingestion runs
asynchronously via Celery (apps.ingestion.tasks.run_ingestion_pipeline_task)
— the view returns as soon as the task is enqueued, without waiting for
extraction, chunking, or embedding to complete.

# NEW LOGIC:
DRF views for document upload and status retrieval.

DocumentUploadView delegates file persistence, Document creation, and
task enqueueing to apps.documents.services.create_document_and_enqueue —
extracted in Milestone 10 once a second caller (the portal's HTML
upload page) needed the exact same logic.

"""

from __future__ import annotations

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document
from .serializers import DocumentDetailSerializer, DocumentUploadSerializer
from .services import create_document_and_enqueue


class DocumentUploadView(APIView):
    """POST /api/documents/ — returns 202 immediately after enqueueing."""

    def post(self, request, *args, **kwargs) -> Response:
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        name = serializer.validated_data.get("name") or uploaded_file.name
        document = create_document_and_enqueue(uploaded_file, name)

        return Response(
            DocumentDetailSerializer(document).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentDetailView(generics.RetrieveAPIView):
    """GET /api/documents/{id}/"""

    queryset = Document.objects.all()
    serializer_class = DocumentDetailSerializer
    lookup_field = "id"