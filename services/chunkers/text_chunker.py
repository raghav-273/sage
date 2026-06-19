# services/chunkers/text_chunker.py
"""
Token-based text chunking service.

Design:
    Pure functions (split_into_token_windows, detect_section_identifier,
    build_chunks_for_page) operate on strings and token-id lists only —
    no Django import, no database access. They are independently
    unit-testable.

    chunk_document() is the only orchestration function. It reads
    DocumentPage rows in page order and persists ContentChunk rows.
    Django imports are deferred inside this function.

Chunking constraint:
    ContentChunk.page is a single required FK — chunks cannot span a page
    boundary. Each page's text is windowed independently; the overlap
    window resets at every page boundary. This is a consequence of the
    current schema, not an independent design choice.

Idempotency:
    All existing ContentChunk rows for the document are deleted and
    recreated inside a single transaction. This is the only strategy that
    is correct when re-chunking produces a different chunk count than a
    previous run (e.g. source text changed), since chunk_index must remain
    a dense, gap-free sequence per the unique_together constraint.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

logger = logging.getLogger("services.chunkers.text_chunker")

CHUNK_MAX_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50
TOKENIZER_ENCODING_NAME = "cl100k_base"

# Matches section identifiers at the start of a line:
#   "4", "4.2", "4.2.1", "Clause 3.4.2", "Section 7.1"
# Heuristic limitation: a line that happens to start with a bare number
# unrelated to a heading (e.g. "100 MPa is required...") will also match.
# This mirrors the known risk already flagged in the architecture document
# (Section 13.2) — no fallback is applied here; section_identifier is
# simply left null when no match is found, which is a nullable field.
SECTION_IDENTIFIER_PATTERN = re.compile(
    r"(?im)^\s*(?:(?:clause|section)\s+)?(?P<identifier>\d{1,3}(?:\.\d{1,3}){0,3})(?=[\s.:)\-]|$)"
)


class ChunkingError(Exception):
    """Raised when chunking fails for a document."""


@dataclass
class ChunkCandidate:
    """One chunk's data prior to persistence. Pure data, no DB ties."""

    page_number: int  # 1-indexed; used to resolve the DocumentPage FK
    chunk_text: str
    token_count: int
    section_identifier: str | None


@dataclass
class ChunkingResult:
    """Summary returned by chunk_document() for logging and task results."""

    document_id: uuid.UUID
    pages_processed: int
    pages_skipped_empty: int
    chunks_created: int


# ── Pure chunking functions — no Django dependency ───────────────────────────


@lru_cache(maxsize=1)
def get_encoding() -> tiktoken.Encoding:
    """Returns the cl100k_base tokenizer, loaded once per process."""
    return tiktoken.get_encoding(TOKENIZER_ENCODING_NAME)


def split_into_token_windows(
    token_ids: list[int],
    max_tokens: int = CHUNK_MAX_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[list[int]]:
    """
    Split a list of token ids into overlapping windows.

    Each window has at most max_tokens ids. Consecutive windows overlap
    by overlap_tokens ids, except there is exactly one final window that
    may be shorter than max_tokens (no padding).

    Raises:
        ChunkingError: if overlap_tokens >= max_tokens, which would not
            guarantee forward progress.
    """
    if overlap_tokens >= max_tokens:
        raise ChunkingError(
            f"overlap_tokens ({overlap_tokens}) must be smaller than "
            f"max_tokens ({max_tokens})"
        )

    if not token_ids:
        return []

    windows: list[list[int]] = []
    step = max_tokens - overlap_tokens
    start = 0
    total = len(token_ids)

    while start < total:
        end = min(start + max_tokens, total)
        windows.append(token_ids[start:end])
        if end == total:
            break
        start += step

    return windows


def detect_section_identifier(text: str) -> str | None:
    """Returns the first section/clause identifier found in text, or None."""
    match = SECTION_IDENTIFIER_PATTERN.search(text)
    return match.group("identifier") if match else None


def build_chunks_for_page(
    page_number: int,
    page_text: str,
    max_tokens: int = CHUNK_MAX_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[ChunkCandidate]:
    """
    Tokenize a single page's text and split it into ChunkCandidates.

    Returns an empty list if page_text is empty or whitespace-only.

    Raises:
        ChunkingError: if any produced chunk exceeds max_tokens (defensive
            check; should be unreachable given the windowing logic above).
    """
    if not page_text or not page_text.strip():
        return []

    encoding = get_encoding()
    token_ids = encoding.encode(page_text)
    windows = split_into_token_windows(token_ids, max_tokens, overlap_tokens)

    candidates: list[ChunkCandidate] = []
    for window in windows:
        if len(window) > max_tokens:
            raise ChunkingError(
                f"Produced chunk with {len(window)} tokens, exceeding "
                f"max_tokens={max_tokens} on page {page_number}"
            )

        chunk_text = encoding.decode(window)
        candidates.append(
            ChunkCandidate(
                page_number=page_number,
                chunk_text=chunk_text,
                token_count=len(window),
                section_identifier=detect_section_identifier(chunk_text),
            )
        )

    return candidates


# ── Orchestration — the only function in this module that touches Django ────


def chunk_document(document_id: uuid.UUID) -> ChunkingResult:
    """
    Chunk every page of a Document and persist ContentChunk records.

    Reads DocumentPage rows in page order, builds chunks per page via
    build_chunks_for_page(), then deletes and recreates all ContentChunk
    rows for the document inside a single transaction.

    Raises:
        ChunkingError: if the document has no pages, or persistence fails.
    """
    # Deferred import: keeps the pure functions above importable without
    # Django configured (e.g. in a standalone unit test process).
    from django.db import transaction

    from apps.chunks.models import ContentChunk
    from apps.documents.models import Document, DocumentPage

    logger.info("chunking_started document_id=%s", document_id)

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist as exc:
        raise ChunkingError(f"Document {document_id} does not exist") from exc

    pages = list(
        DocumentPage.objects.filter(document=document).order_by("page_number")
    )
    if not pages:
        raise ChunkingError(
            f"Document {document_id} has no DocumentPage records — "
            f"run extraction before chunking."
        )

    pages_processed = 0
    pages_skipped_empty = 0
    chunk_rows: list[ContentChunk] = []
    chunk_index = 0

    for page in pages:
        candidates = build_chunks_for_page(page.page_number, page.raw_text)

        if not candidates:
            pages_skipped_empty += 1
            logger.debug(
                "page_skipped_empty document_id=%s page_number=%d",
                document_id, page.page_number,
            )
            continue

        pages_processed += 1
        for candidate in candidates:
            chunk_rows.append(
                ContentChunk(
                    document=document,
                    page=page,
                    chunk_index=chunk_index,
                    chunk_text=candidate.chunk_text,
                    chunk_type=ContentChunk.ChunkType.TEXT,
                    section_identifier=candidate.section_identifier,
                    token_count=candidate.token_count,
                )
            )
            chunk_index += 1

    try:
        with transaction.atomic():
            # Delete-then-recreate: the only strategy that correctly
            # handles a re-run producing fewer chunks than the previous
            # run (see module docstring).
            deleted_count, _ = ContentChunk.objects.filter(document=document).delete()
            ContentChunk.objects.bulk_create(chunk_rows)
    except Exception as exc:
        raise ChunkingError(
            f"Persistence failed for document {document_id}: {exc}"
        ) from exc

    result = ChunkingResult(
        document_id=document.id,
        pages_processed=pages_processed,
        pages_skipped_empty=pages_skipped_empty,
        chunks_created=len(chunk_rows),
    )

    logger.info(
        "chunking_completed document_id=%s pages_processed=%d pages_skipped_empty=%d "
        "chunks_created=%d previous_chunks_deleted=%d",
        document_id, pages_processed, pages_skipped_empty, len(chunk_rows), deleted_count,
    )

    return result