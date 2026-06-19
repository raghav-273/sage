# services/retrieval/rrf.py
"""
Reciprocal Rank Fusion (RRF) for combining multiple ranked result lists.

Formula: for each ranked list a chunk appears in, contribute 1/(k+rank),
where rank is 1-indexed. A chunk's fused score is the sum of its
contributions across every list it appears in — this is both the
deduplication mechanism (one dict entry per chunk_id) and what guarantees
the combined score reflects every appearance rather than just one.
"""

from __future__ import annotations

import uuid

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[uuid.UUID]],
    k: int = DEFAULT_RRF_K,
) -> list[tuple[uuid.UUID, float]]:
    """
    Fuse multiple ranked lists of chunk_ids into a single ranked list.

    Args:
        ranked_lists: each inner list is ordered best-to-worst (index 0 =
            rank 1). Lists may differ in length and may overlap.
        k: the RRF constant.

    Returns:
        (chunk_id, fused_score) tuples, deduplicated, sorted descending.

    Raises:
        ValueError: if k is not positive.
    """
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    fused_scores: dict[uuid.UUID, float] = {}

    for ranked_list in ranked_lists:
        for position, chunk_id in enumerate(ranked_list):
            rank = position + 1
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / (k + rank)

    return sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)