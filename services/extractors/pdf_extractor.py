# services/extractors/pdf_extractor.py
"""
PyMuPDF-based PDF extraction service.

Design:
    Pure functions (extract_pdf, extract_page_text, extract_page_images)
    operate on fitz objects and filesystem paths only — no Django import,
    no database access. They are independently unit-testable.

    extract_document() is the only orchestration function. It loads the
    Document, calls the pure functions, and persists DocumentPage and
    DiagramAsset records. Django imports are deferred inside this function
    so the pure functions above remain importable without Django configured.

Idempotency:
    - DocumentPage: update_or_create on (document, page_number). Re-running
      extraction for the same document updates existing rows in place;
      no duplicate pages are created.
    - DiagramAsset: deduplicated by a deterministic image_path
      (page number + PDF xref). Re-running extraction skips images whose
      path already has a matching DiagramAsset row, and does not
      re-write the file to disk.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger("services.extractors.pdf_extractor")


class PDFExtractionError(Exception):
    """Raised when PDF extraction fails for a document."""


@dataclass
class ExtractedImage:
    """One image extracted from a single PDF page. Pure data, no DB ties."""

    page_number: int  # 1-indexed
    xref: int  # PyMuPDF cross-reference number; used for dedup
    image_bytes: bytes
    image_ext: str  # e.g. "png", "jpeg"
    width: int
    height: int
    bbox: tuple[float, float, float, float] | None  # (x0, y0, x1, y1) in PDF points


@dataclass
class ExtractedPage:
    """One page's extracted text and images. Pure data, no DB ties."""

    page_number: int  # 1-indexed
    text: str
    images: list[ExtractedImage]


@dataclass
class ExtractionResult:
    """Summary returned by extract_document() for logging and task results."""

    document_id: uuid.UUID
    page_count: int
    pages_created: int
    pages_updated: int
    images_created: int
    images_skipped: int


# ── Pure extraction functions — no Django dependency ─────────────────────────


def extract_page_text(page: fitz.Page) -> str:
    """Extract plain text from a single PyMuPDF page."""
    return page.get_text("text") or ""


def extract_page_images(
    pdf_doc: fitz.Document, page: fitz.Page, page_number: int
) -> list[ExtractedImage]:
    """
    Extract embedded images from a single page.

    Enumerates image xrefs via page.get_images(full=True), then retrieves
    raw bytes via pdf_doc.extract_image(xref). Bounding box is resolved via
    page.get_image_rects(xref) when PyMuPDF can locate it; some embedded
    images cannot be geometrically located, in which case bbox is None.

    A single xref is extracted at most once per page, since the same
    embedded image can be referenced multiple times (e.g. a repeated logo).
    """
    images: list[ExtractedImage] = []
    seen_xrefs: set[int] = set()

    for img_info in page.get_images(full=True):
        xref = img_info[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        try:
            base_image = pdf_doc.extract_image(xref)
        except Exception as exc:
            logger.warning(
                "image_extract_failed page=%s xref=%s error=%s",
                page_number, xref, exc,
            )
            continue

        bbox: tuple[float, float, float, float] | None = None
        try:
            rects = page.get_image_rects(xref)
            if rects:
                r = rects[0]
                bbox = (r.x0, r.y0, r.x1, r.y1)
        except Exception:
            bbox = None

        images.append(
            ExtractedImage(
                page_number=page_number,
                xref=xref,
                image_bytes=base_image["image"],
                image_ext=base_image.get("ext", "png"),
                width=base_image.get("width", 0),
                height=base_image.get("height", 0),
                bbox=bbox,
            )
        )

    return images


def extract_pdf(file_path: Path) -> list[ExtractedPage]:
    """
    Extract text and images from every page of a PDF.

    Pure function: takes a filesystem path, returns in-memory data.
    Performs no database access.

    Raises:
        PDFExtractionError: if the file is missing or cannot be parsed.
    """
    if not file_path.exists():
        raise PDFExtractionError(f"PDF file not found at {file_path}")

    try:
        pdf_doc = fitz.open(str(file_path))
    except Exception as exc:
        raise PDFExtractionError(f"Failed to open PDF at {file_path}: {exc}") from exc

    pages: list[ExtractedPage] = []
    try:
        for page_index in range(pdf_doc.page_count):
            page = pdf_doc[page_index]
            page_number = page_index + 1

            try:
                text = extract_page_text(page)
            except Exception as exc:
                raise PDFExtractionError(
                    f"Failed to extract text on page {page_number}: {exc}"
                ) from exc

            try:
                images = extract_page_images(pdf_doc, page, page_number)
            except Exception as exc:
                raise PDFExtractionError(
                    f"Failed to extract images on page {page_number}: {exc}"
                ) from exc

            pages.append(ExtractedPage(page_number=page_number, text=text, images=images))
    finally:
        pdf_doc.close()

    logger.info("pdf_extracted path=%s page_count=%d", file_path, len(pages))
    return pages


# ── Orchestration — the only function in this module that touches Django ────


def extract_document(document_id: uuid.UUID) -> ExtractionResult:
    """
    Extract a Document's PDF and persist DocumentPage / DiagramAsset records.

    Loads the Document, runs extract_pdf() against its file_path, then
    writes results inside a single transaction. Extracted images are
    written to MEDIA_ROOT/{IMAGES_UPLOAD_DIR}/{document_id}/.

    Idempotent: safe to call multiple times for the same document_id.
    See module docstring for the exact dedup strategy.

    Raises:
        PDFExtractionError: if the Document does not exist, the PDF file
            is missing, or extraction/persistence fails.
    """
    # Deferred import: keeps the pure functions above importable without
    # Django configured (e.g. in a standalone unit test process).
    from django.conf import settings
    from django.db import transaction

    from apps.chunks.models import DiagramAsset
    from apps.documents.models import Document, DocumentPage

    logger.info("extraction_started document_id=%s", document_id)

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist as exc:
        raise PDFExtractionError(f"Document {document_id} does not exist") from exc

    pdf_path = Path(settings.MEDIA_ROOT) / document.file_path
    extracted_pages = extract_pdf(pdf_path)

    images_dir = Path(settings.MEDIA_ROOT) / settings.IMAGES_UPLOAD_DIR / str(document.id)
    images_dir.mkdir(parents=True, exist_ok=True)

    pages_created = 0
    pages_updated = 0
    images_created = 0
    images_skipped = 0

    try:
        with transaction.atomic():
            for extracted_page in extracted_pages:
                page_obj, created = DocumentPage.objects.update_or_create(
                    document=document,
                    page_number=extracted_page.page_number,
                    defaults={
                        "raw_text": extracted_page.text,
                        "has_images": len(extracted_page.images) > 0,
                        "has_tables": False,  # table detection is out of scope for this milestone
                    },
                )
                pages_created += 1 if created else 0
                pages_updated += 0 if created else 1

                for image in extracted_page.images:
                    # Deterministic path → idempotent on disk and in the DB.
                    image_filename = f"page_{image.page_number}_xref_{image.xref}.{image.image_ext}"
                    relative_image_path = str(
                        Path(settings.IMAGES_UPLOAD_DIR) / str(document.id) / image_filename
                    )

                    if DiagramAsset.objects.filter(
                        document=document, page=page_obj, image_path=relative_image_path
                    ).exists():
                        images_skipped += 1
                        continue

                    absolute_image_path = Path(settings.MEDIA_ROOT) / relative_image_path
                    try:
                        absolute_image_path.write_bytes(image.image_bytes)
                    except OSError as exc:
                        raise PDFExtractionError(
                            f"Failed to write image to {absolute_image_path}: {exc}"
                        ) from exc

                    bounding_box = None
                    if image.bbox is not None:
                        x0, y0, x1, y1 = image.bbox
                        bounding_box = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}

                    DiagramAsset.objects.create(
                        document=document,
                        page=page_obj,
                        image_path=relative_image_path,
                        image_format=image.image_ext.upper(),
                        width_px=image.width or None,
                        height_px=image.height or None,
                        caption=None,  # caption detection is out of scope for this milestone
                        ocr_text=None,  # OCR is out of scope for this milestone
                        bounding_box=bounding_box,
                    )
                    images_created += 1

            document.page_count = len(extracted_pages)
            document.save(update_fields=["page_count"])

    except PDFExtractionError:
        raise
    except Exception as exc:
        raise PDFExtractionError(
            f"Persistence failed for document {document_id}: {exc}"
        ) from exc

    result = ExtractionResult(
        document_id=document.id,
        page_count=len(extracted_pages),
        pages_created=pages_created,
        pages_updated=pages_updated,
        images_created=images_created,
        images_skipped=images_skipped,
    )

    logger.info(
        "extraction_completed document_id=%s pages_created=%d pages_updated=%d "
        "images_created=%d images_skipped=%d",
        document_id, pages_created, pages_updated, images_created, images_skipped,
    )

    return result