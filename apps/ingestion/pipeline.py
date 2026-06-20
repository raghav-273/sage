# apps/ingestion/pipeline.py
"""
Ingestion orchestration: ties extraction, chunking, and embedding
generation together and drives Document.status through its lifecycle.

Root cause this resolves: neither extract_document() nor chunk_document()
were ever designed to touch Document.status — that responsibility was
always intended to live here, but this file was never written because
Celery task wiring was explicitly out of scope in every prior milestone.

This is a plain, synchronous function — not a Celery task. Wrapping it
for async execution is a separate, future change; this fix resolves only
the missing status transition, per the stated scope of this investigation.

Includes embedding generation as a required stage (not an unrelated
addition): chunk_document() does not embed chunks, and a pipeline that
only fixed status (extract -> chunk -> READY) would mark documents READY
with NULL embeddings, which vector_search explicitly excludes
(embedding__isnull=False) — reproducing the same user-facing symptom
through a different cause.
"""

from __future__ import annotations

import logging
import uuid

from services.chunkers.text_chunker import chunk_document
from services.extractors.pdf_extractor import extract_document
from services.llm_client.base import EmbeddingClient

logger = logging.getLogger("apps.ingestion.pipeline")


class IngestionPipelineError(Exception):
    """Raised when the ingestion pipeline fails at any stage."""


def _default_embedding_client() -> EmbeddingClient:
    """
    Lazily resolves the project's default embedding client.

    Deferred import: avoids loading sentence-transformers unless this
    pipeline runs without an explicit embedding_client — e.g. never, in
    tests that inject a fake client.
    """
    from services.llm_client.sentence_transformer_client import (
        SentenceTransformerEmbeddingClient,
    )

    return SentenceTransformerEmbeddingClient()


def _generate_embeddings_for_document(
    document_id: uuid.UUID, embedding_client: EmbeddingClient
) -> int:
    """
    Embeds every ContentChunk for this document that doesn't already have
    an embedding. Returns the number of chunks embedded.
    """
    from apps.chunks.models import ContentChunk

    chunks = list(ContentChunk.objects.filter(document_id=document_id, embedding__isnull=True))
    if not chunks:
        return 0

    vectors = embedding_client.embed([chunk.chunk_text for chunk in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector
        chunk.save(update_fields=["embedding"])

    return len(chunks)


def run_ingestion_pipeline(
    document_id: uuid.UUID,
    embedding_client: EmbeddingClient | None = None,
) -> None:
    """
    Runs extraction, chunking, and embedding generation for a Document,
    driving its status through EXTRACTING -> CHUNKING -> EMBEDDING ->
    READY. On any failure, status is set to FAILED with error_message
    populated, and the original exception is re-raised.

    Args:
        document_id: the Document to process. Must already have a valid
            file_path (the PDF must already be saved to disk — this
            function does not handle upload).
        embedding_client: optional EmbeddingClient override, for testing.
            Defaults to the project's local sentence-transformers client.

    Raises:
        IngestionPipelineError: wraps any underlying exception. The
            Document is marked FAILED with error_message set before this
            is raised.
    """
    from apps.documents.models import Document

    document = Document.objects.get(id=document_id)

    try:
        document.status = Document.Status.EXTRACTING
        document.save(update_fields=["status"])
        logger.info("ingestion_stage document_id=%s stage=EXTRACTING", document_id)
        extract_document(document_id)

        document.status = Document.Status.CHUNKING
        document.save(update_fields=["status"])
        logger.info("ingestion_stage document_id=%s stage=CHUNKING", document_id)
        chunk_document(document_id)

        document.status = Document.Status.EMBEDDING
        document.save(update_fields=["status"])
        logger.info("ingestion_stage document_id=%s stage=EMBEDDING", document_id)
        client = embedding_client or _default_embedding_client()
        embedded_count = _generate_embeddings_for_document(document_id, client)
        logger.info(
            "ingestion_embedding_completed document_id=%s chunks_embedded=%d",
            document_id, embedded_count,
        )

        document.status = Document.Status.READY
        document.save(update_fields=["status"])
        logger.info("ingestion_completed document_id=%s status=READY", document_id)

    except Exception as exc:
        logger.error(
            "ingestion_failed document_id=%s last_stage=%s error=%s",
            document_id, document.status, exc,
        )
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message"])
        raise IngestionPipelineError(
            f"Ingestion failed for document {document_id}: {exc}"
        ) from exc