# apps/chunks/models.py
"""
Models for the chunks app.

ContentChunk — the core retrieval unit. Carries a pgvector embedding column.
              No vector index is defined; exact search (<=> operator,
              sequential scan) is used per architecture v1.1. An IVFFlat
              index can be added later as a single additive migration.

DiagramAsset — extracted image metadata only. No embedding field — removed
               in architecture v1.1. Stores path, dimensions, caption,
               OCR text, and bounding box.
"""

import uuid

from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.documents.models import Document, DocumentPage


class ContentChunk(models.Model):
    """A semantically meaningful text slice with an optional vector embedding."""

    class ChunkType(models.TextChoices):
        TEXT = "text", "Text"
        TABLE = "table", "Table"
        CAPTION = "caption", "Caption"
        HEADING = "heading", "Heading"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    page = models.ForeignKey(
        DocumentPage,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    chunk_index = models.PositiveIntegerField(
        help_text="0-based, monotonically increasing per document."
    )
    chunk_text = models.TextField()
    chunk_type = models.CharField(
        max_length=20,
        choices=ChunkType.choices,
        default=ChunkType.TEXT,
    )
    section_identifier = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='e.g. "4.3.2". Null if no heading structure was detected.',
    )
    token_count = models.PositiveIntegerField(default=0)

    # pgvector column. NULL until the embedding milestone populates it.
    # No index — exact search per architecture v1.1.
    embedding = VectorField(
        dimensions=settings.PGVECTOR_EMBEDDING_DIMENSIONS,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="uniq_document_chunk_index",
            ),
        ]
        indexes = [
            models.Index(fields=["section_identifier"], name="chunk_section_idx"),
        ]

    def __str__(self) -> str:
        return f"Chunk {self.chunk_index} of {self.document.name}"


class DiagramAsset(models.Model):
    """
    Metadata for an extracted image (diagram, schematic, figure).

    No embedding field. Per architecture v1.1, DiagramAsset is
    metadata-only: path, dimensions, caption, OCR text, bounding box.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="diagrams",
    )
    page = models.ForeignKey(
        DocumentPage,
        on_delete=models.CASCADE,
        related_name="diagrams",
    )

    # Relative path under MEDIA_ROOT, e.g. "images/3fa85f64.../page_12_img_3.png"
    image_path = models.CharField(max_length=500)
    image_format = models.CharField(max_length=20, default="PNG")
    width_px = models.PositiveIntegerField(null=True, blank=True)
    height_px = models.PositiveIntegerField(null=True, blank=True)

    caption = models.TextField(
        null=True,
        blank=True,
        help_text="Nearest text identified as a figure caption, if any.",
    )
    ocr_text = models.TextField(
        null=True,
        blank=True,
        help_text="Text detected inside the image, if any.",
    )
    bounding_box = models.JSONField(
        null=True,
        blank=True,
        help_text="{x, y, width, height} in PDF points.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "page"]
        indexes = [
            models.Index(fields=["document"], name="diagram_document_idx"),
        ]

    def __str__(self) -> str:
        return f"Diagram on page {self.page.page_number} of {self.document.name}"