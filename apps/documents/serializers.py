# apps/documents/serializers.py
"""
Serializers for document upload validation and status/metadata output.

DocumentUploadSerializer validates input only — it does not create the
Document record. Creating the record requires writing the uploaded file
to disk first to compute file_path and file_size_bytes, which is a
side effect a serializer's validate() step shouldn't own; that's the
view's job.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from .models import Document


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_file(self, value):
        if value.content_type != "application/pdf":
            raise serializers.ValidationError("Only PDF files are accepted.")
        if value.size > settings.MAX_UPLOAD_SIZE_BYTES:
            max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"File exceeds maximum size of {max_mb} MB.")
        return value


class DocumentDetailSerializer(serializers.ModelSerializer):
    """
    Read-only representation of Document status/metadata.

    Includes chunk_count (computed) beyond the minimum spec — a small,
    genuinely useful superset, consistent with how every other response
    schema in this project has been built.
    """

    document_id = serializers.UUIDField(source="id", read_only=True)
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "document_id", "name", "status", "page_count",
            "chunk_count", "error_message", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_chunk_count(self, obj: Document) -> int:
        return obj.chunks.count()