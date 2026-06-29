# apps/conversation/services.py
"""
Orchestrates document-scoped conversation sessions: get-or-create the
active session, pull the recent turn window, call generate_answer with
that history, persist the new turn.
"""

from __future__ import annotations

from dataclasses import asdict

from django.conf import settings
from django.contrib.auth.models import User

from apps.documents.models import Document
from services.generation.answer_rendering import render_answer_with_numbered_citations
from services.generation.generation_service import generate_answer

from .models import ConversationTurn, DocumentSession


def get_or_create_active_session(document: Document, user: User) -> DocumentSession:
    session, _ = DocumentSession.objects.get_or_create(document=document, user=user, is_active=True)
    return session


def _conversation_window_size() -> int:
    return getattr(settings, "CONVERSATION_HISTORY_WINDOW", 3)


def get_recent_turns(session: DocumentSession) -> list[ConversationTurn]:
    """Returns up to the last N turns for this session, oldest first."""
    window = _conversation_window_size()
    recent = list(session.turns.order_by("-turn_index")[:window])
    return list(reversed(recent))


def ask_in_session(session: DocumentSession, query: str) -> ConversationTurn:
    """
    Runs retrieval+generation for `query`, scoped to session.document,
    with the session's recent turns included as conversational context.
    Persists and returns the new turn.
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


def clear_session(session: DocumentSession) -> DocumentSession:
    """Deactivates the current session and returns a fresh, empty one."""
    session.is_active = False
    session.save(update_fields=["is_active"])
    return get_or_create_active_session(session.document, session.user)