# apps/ingestion/pipeline.py
"""
Ingestion orchestration: extraction → chunking → captioning → embedding → READY.

CAPTIONING stage (added in Milestone 13C):
    Generates captions for DiagramAssets via Gemini's vision API and stores
    them as ContentChunk records with chunk_type=CAPTION, linked back to their
    source DiagramAsset.

    Idempotency: captions are stored on DiagramAsset.caption. On re-runs,
    ContentChunks are rebuilt from that stored text without calling Gemini
    again — so Gemini is called at most once per image across all pipeline runs.

    text_chunker.chunk_document() deletes and recreates all ContentChunks
    (unchanged from Milestone 4) — including any CAPTION chunks from a prior
    run. CAPTIONING then recreates them from DiagramAsset.caption, so the
    dense chunk_index sequence remains collision-free.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from services.chunkers.text_chunker import chunk_document
from services.extractors.pdf_extractor import extract_document
from services.llm_client.base import EmbeddingClient

logger = logging.getLogger("apps.ingestion.pipeline")


class IngestionPipelineError(Exception):
    """Raised when the ingestion pipeline fails at any stage."""


def _default_embedding_client() -> EmbeddingClient:
    from services.llm_client.sentence_transformer_client import SentenceTransformerEmbeddingClient
    return SentenceTransformerEmbeddingClient()


def _generate_embeddings_for_document(
    document_id: uuid.UUID, embedding_client: EmbeddingClient
) -> int:
    """Embeds every ContentChunk (any type) that doesn't yet have an embedding."""
    from apps.chunks.models import ContentChunk

    chunks = list(ContentChunk.objects.filter(document_id=document_id, embedding__isnull=True))
    if not chunks:
        return 0

    vectors = embedding_client.embed([chunk.chunk_text for chunk in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector
        chunk.save(update_fields=["embedding"])

    return len(chunks)


def _generate_captions_for_document(document_id: uuid.UUID) -> int:
    """
    Generates captions for each DiagramAsset in this document.

    Strategy:
    - If DiagramAsset.caption is already set (from a prior run), recreate the
      ContentChunk from that text without calling Gemini.
    - If DiagramAsset.caption is None, call Gemini vision. On success, store
      the caption on DiagramAsset.caption AND create a ContentChunk.
    - Any single-image failure is logged and skipped; pipeline continues.

    Caption ContentChunks are assigned chunk_index values starting immediately
    after the current max (set by text chunking), so no collision is possible.
    """
    from django.conf import settings
    from django.db.models import Max

    from apps.chunks.models import ContentChunk, DiagramAsset
    from apps.documents.models import Document
    from services.generation.image_captioner import generate_caption

    document = Document.objects.get(id=document_id)
    diagrams = list(
        DiagramAsset.objects.filter(document=document).select_related("page").order_by("page__page_number")
    )
    if not diagrams:
        return 0

    existing_max = ContentChunk.objects.filter(document=document).aggregate(
        max_index=Max("chunk_index")
    )["max_index"]
    chunk_index = (existing_max + 1) if existing_max is not None else 0

    captions_created = 0
    for diagram in diagrams:
        # Use stored caption (from a prior run) without calling Gemini.
        caption_text = diagram.caption

        if caption_text is None:
            image_path = Path(settings.MEDIA_ROOT) / diagram.image_path
            ext = image_path.suffix.lower().lstrip(".")
            mime_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}" if ext else "image/png"

            caption_text = generate_caption(image_path, mime_type=mime_type)
            if caption_text is None:
                continue

            # Persist so re-runs don't need to call Gemini again.
            diagram.caption = caption_text
            diagram.save(update_fields=["caption"])

        ContentChunk.objects.create(
            document=document,
            page=diagram.page,
            chunk_index=chunk_index,
            chunk_text=caption_text,
            chunk_type=ContentChunk.ChunkType.CAPTION,
            section_identifier=None,
            token_count=0,
            diagram_asset=diagram,
        )
        chunk_index += 1
        captions_created += 1

    return captions_created


def run_ingestion_pipeline(
    document_id: uuid.UUID,
    embedding_client: EmbeddingClient | None = None,
) -> None:
    """
    Runs the complete ingestion pipeline for a Document:
        EXTRACTING → CHUNKING → CAPTIONING → EMBEDDING → READY
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

        document.status = Document.Status.CAPTIONING
        document.save(update_fields=["status"])
        logger.info("ingestion_stage document_id=%s stage=CAPTIONING", document_id)
        caption_count = _generate_captions_for_document(document_id)
        logger.info(
            "ingestion_captioning_completed document_id=%s captions_generated=%d",
            document_id, caption_count,
        )

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