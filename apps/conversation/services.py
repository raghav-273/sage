# apps/conversation/services.py
"""
Orchestrates document-scoped investigation sessions.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict

from django.conf import settings
from django.contrib.auth.models import User

from apps.documents.models import Document
from services.generation.answer_rendering import render_answer_with_numbered_citations
from services.generation.generation_service import generate_answer

from .models import ConversationTurn, DocumentSession


def _default_investigation_title() -> str:
    return f"Investigation — {datetime.date.today().strftime('%B %d, %Y')}"


def get_or_create_active_session(
    document: Document,
    user: User,
    title: str = "",
) -> DocumentSession:
    """
    Returns the active session for this document/user, creating one if none
    exists. When creating, uses the provided title or a date-based default.
    """
    session, _ = DocumentSession.objects.get_or_create(
        document=document,
        user=user,
        is_active=True,
        defaults={"title": title or _default_investigation_title()},
    )
    return session


def _conversation_window_size() -> int:
    return getattr(settings, "CONVERSATION_HISTORY_WINDOW", 3)


def get_recent_turns(session: DocumentSession) -> list[ConversationTurn]:
    window = _conversation_window_size()
    recent = list(session.turns.order_by("-turn_index")[:window])
    return list(reversed(recent))


def ask_in_session(session: DocumentSession, query: str) -> ConversationTurn:
    """
    Runs retrieval+generation for `query`, scoped to session.document,
    with the session's recent turns included as conversational context.
    Persists and returns the new ConversationTurn (finding).
    """
    recent_turns = get_recent_turns(session)
    prior_turns = [(turn.query_text, turn.answer_text) for turn in recent_turns]

    result = generate_answer(
        query=query,
        document_ids=[session.document_id],
        prior_turns=prior_turns or None,
    )

    rendered_answer = render_answer_with_numbered_citations(result)
    next_index = (recent_turns[-1].turn_index + 1) if recent_turns else 0

    return ConversationTurn.objects.create(
        session=session,
        turn_index=next_index,
        query_text=query,
        answer_text=rendered_answer,
        has_valid_citations=result.has_valid_citations,
        retrieved_chunk_count=result.retrieved_chunk_count,
        citations=[asdict(citation) for citation in result.citations],
    )


def clear_session(session: DocumentSession) -> None:
    """Deactivates the current session. Next visit starts a fresh one."""
    session.is_active = False
    session.save(update_fields=["is_active"])