# apps/documents/models.py
"""
Models for the documents app.

Document     — lifecycle record for an uploaded PDF (upload → ingestion → ready).
DocumentPage — one row per extracted page; the page-number anchor for citations.

No binary file content is stored in PostgreSQL. file_path and image_path
(in apps.chunks) store relative paths under MEDIA_ROOT only.
"""

import uuid

from django.db import models


class Document(models.Model):
    """A PDF uploaded for ingestion, tracked through every processing stage."""

    class Status(models.TextChoices):
        """
        Ingestion lifecycle. Transitions are written by Celery tasks
        (apps.ingestion.tasks), never by the API layer directly.
        """
        PENDING = "PENDING", "Pending"
        QUEUED = "QUEUED", "Queued"
        EXTRACTING = "EXTRACTING", "Extracting"
        CHUNKING = "CHUNKING", "Chunking"
        CAPTIONING = "CAPTIONING", "Captioning"
        EMBEDDING = "EMBEDDING", "Embedding"
        GRAPHING = "GRAPHING", "Graphing"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        max_length=255,
        help_text="Display name. Defaults to original_filename if not supplied at upload.",
    )
    original_filename = models.CharField(max_length=255)

    # Relative path under MEDIA_ROOT, e.g. "documents/3fa85f64-....pdf"
    # The PDF binary itself is never stored in PostgreSQL.
    file_path = models.CharField(max_length=500)
    file_size_bytes = models.BigIntegerField()
    mime_type = models.CharField(max_length=100, default="application/pdf")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    page_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Populated after extract_text_and_tables completes.",
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Set when status=FAILED. Human-readable failure description.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="doc_status_idx"),
            models.Index(fields=["-created_at"], name="doc_created_idx"),
        ]
    @property
    def is_terminal(self) -> bool:
        """
        True once ingestion has reached a final state — no further
        automatic status transition will occur. Drives the portal's
        self-canceling HTMX status-polling pattern: while False, the
        status partial includes hx-trigger; once True, it doesn't.
        Plain property — no migration, no schema change.
        """
        return self.status in (Document.Status.READY, Document.Status.FAILED)
    
    def __str__(self) -> str:
        return f"{self.name} [{self.status}]"


class DocumentPage(models.Model):
    """
    One row per extracted PDF page.

    raw_text is the full PyMuPDF text extraction for that page.
    Full-text search indexing (TSVECTOR + GIN) is deferred to the
    retrieval milestone; raw_text is stored in full now so no
    re-extraction is needed when that lands.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="pages",
    )
    page_number = models.PositiveIntegerField(help_text="1-indexed page number.")

    raw_text = models.TextField(blank=True, default="")

    has_images = models.BooleanField(
        default=False,
        help_text="True if ≥1 DiagramAsset was extracted from this page.",
    )
    has_tables = models.BooleanField(
        default=False,
        help_text="True if ≥1 table was detected on this page.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "page_number"],
                name="uniq_document_page_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document.name} — page {self.page_number}"