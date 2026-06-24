# apps/portal/answer_rendering.py
"""
Presentation-only transform: replaces [CITE:chunk_id] markers in an
AnswerResult's raw answer_text with numbered references matching the
citation list rendered below it in the portal's HTML.

Deliberately NOT applied in services.generation.generation_service or
apps.api — the JSON API's answer_text stays raw, exactly as documented
when AnswerResult was first designed. A future mobile client may want to
render citations differently; this transform is portal-HTML-specific.
"""

from __future__ import annotations

import re
import uuid

from services.generation.generation_service import AnswerResult

_CITE_MARKER_PATTERN = re.compile(r"\[CITE:([0-9a-fA-F-]{36})\]")


def render_answer_with_numbered_citations(result: AnswerResult) -> str:
    """
    Returns answer_text with [CITE:chunk_id] markers replaced by [n],
    where n is the 1-indexed position of that chunk_id in result.citations.
    A marker referencing a chunk_id not in result.citations — shouldn't
    happen, since citation_validator already rejects those, but this
    function doesn't trust that and strips it rather than rendering a
    raw, broken-looking marker.
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