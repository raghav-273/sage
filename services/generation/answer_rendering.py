# services/generation/answer_rendering.py
"""
Presentation transform: replaces [CITE:chunk_id] markers in an
AnswerResult's raw answer_text with numbered references matching the
citation list rendered alongside it.

Moved here from apps.portal in Milestone 13B once a second consumer
(apps.conversation) needed the same logic — it never had any
portal-specific code in it; framework-independent regex/dataclass logic
belongs in services/, not apps/portal/.

Deliberately NOT applied in services.generation.generation_service or
apps.api — the JSON API's answer_text stays raw. A future mobile client
may want to render citations differently; this transform is for
HTML-rendering consumers (the portal's stateless query page and the
conversation feature) specifically.
"""

from __future__ import annotations

import re
import uuid

from services.generation.generation_service import AnswerResult

_CITE_MARKER_PATTERN = re.compile(r"\[CITE:\s*([0-9a-fA-F-]{36})\]")


def render_answer_with_numbered_citations(result: AnswerResult) -> str:
    """
    Returns answer_text with [CITE:chunk_id] markers replaced by [n],
    where n is the 1-indexed position of that chunk_id in result.citations.
    A marker referencing a chunk_id not in result.citations is stripped
    rather than rendered, since it shouldn't be possible to reach this
    function with one — citation_validator already rejects those — but
    this function doesn't trust that assumption either.
    """
    position_by_chunk_id = {
        citation.chunk_id: index + 1 for index, citation in enumerate(result.citations)
    }

    def _replace(match: re.Match) -> str:
        try:
            chunk_id = uuid.UUID(match.group(1))
        except ValueError:
            return ""
        position = position_by_chunk_id.get(chunk_id)
        return f"[{position}]" if position is not None else ""

    return _CITE_MARKER_PATTERN.sub(_replace, result.answer_text)