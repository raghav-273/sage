# services/generation/citation_validator.py
"""
Parses [CITE:chunk_id] markers from generated text and validates them
against the actual set of retrieved chunks.

ARCHITECTURAL NOTE — image_path enrichment (added Milestone 13C):

The lookup below that populates Citation.image_path for CAPTION chunks
is a deliberate short-term pragmatism, not the intended long-term design.
It introduces ORM access into what should be a pure validation/transform
layer, at the cost of up to top_k extra DB queries per request (~5 max
at current settings).

The correct long-term design is to enrich RetrievedChunk at retrieval
time rather than here:

  1. Add image_path: str | None to RetrievedChunk (retrieval_service.py)
  2. In vector_search() and keyword_search(), .select_related("diagram_asset")
     and populate image_path = chunk.diagram_asset.image_path if
     chunk.chunk_type == CAPTION and chunk.diagram_asset is not None
  3. Remove the ORM lookup block below entirely; citation_validator
     becomes purely: iterate markers → validate IDs → copy metadata
     from RetrievedChunk → return

This change is deferred because it touches 4 stable, tested files in
the retrieval layer with no current pressing need (5 queries per request
is not a bottleneck at current scale). When additional diagram metadata
is needed in citations (bounding boxes, figure numbers, OCR regions),
implement it on RetrievedChunk at that time and remove this block as
part of the same change.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from services.retrieval.retrieval_service import RetrievedChunk

logger = logging.getLogger("services.generation.citation_validator")

CITATION_MARKER_PATTERN = re.compile(r"\[CITE:\s*([0-9a-fA-F-]{36})\]")


@dataclass
class Citation:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    section_identifier: str | None
    excerpt: str
    confidence_score: float
    retrieval_method: str
    image_path: str | None = None


@dataclass
class CitationValidationResult:
    citations: list[Citation]
    rejected_citation_count: int


def _get_image_path_for_chunk(chunk_id: uuid.UUID) -> str | None:
    """
    Returns the image_path for a CAPTION chunk's DiagramAsset, or None.

    Isolated in its own function so the architectural note above is
    visible alongside the call site, and so the refactor described
    there has a single, obvious deletion target.
    """
    try:
        from apps.chunks.models import ContentChunk as _CC
        chunk_obj = _CC.objects.select_related("diagram_asset").get(id=chunk_id)
        if (
            chunk_obj.chunk_type == _CC.ChunkType.CAPTION
            and chunk_obj.diagram_asset is not None
        ):
            return chunk_obj.diagram_asset.image_path
    except Exception:
        pass
    return None


def validate_citations(
    answer_text: str,
    retrieved_chunks: list[RetrievedChunk],
) -> CitationValidationResult:
    """
    Parses every [CITE:chunk_id] marker in answer_text and validates each
    against retrieved_chunks — the only chunks genuinely available to the model.
    """
    chunk_lookup: dict[uuid.UUID, RetrievedChunk] = {c.chunk_id: c for c in retrieved_chunks}

    citations: list[Citation] = []
    seen_chunk_ids: set[uuid.UUID] = set()
    rejected_count = 0

    for match in CITATION_MARKER_PATTERN.finditer(answer_text):
        raw_id = match.group(1)

        try:
            chunk_id = uuid.UUID(raw_id)
        except ValueError:
            logger.warning("citation_rejected reason=malformed_uuid raw=%r", raw_id)
            rejected_count += 1
            continue

        if chunk_id not in chunk_lookup:
            logger.warning("citation_rejected reason=unknown_chunk_id chunk_id=%s", chunk_id)
            rejected_count += 1
            continue

        if chunk_id in seen_chunk_ids:
            continue

        seen_chunk_ids.add(chunk_id)
        source = chunk_lookup[chunk_id]
        image_path = _get_image_path_for_chunk(chunk_id)

        citations.append(
            Citation(
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                page_number=source.page_number,
                section_identifier=source.section_identifier,
                excerpt=source.chunk_text,
                confidence_score=source.retrieval_score,
                retrieval_method=source.retrieval_method,
                image_path=image_path,
            )
        )

    return CitationValidationResult(citations=citations, rejected_citation_count=rejected_count)