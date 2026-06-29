# tests/unit/test_conversation_services.py
"""
Unit tests for apps.conversation.services. generate_answer is mocked —
its own logic is covered elsewhere; these test session lifecycle, turn
windowing, document isolation, and history persistence.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from apps.conversation.models import ConversationTurn
from apps.conversation.services import (
    ask_in_session, clear_session, get_or_create_active_session, get_recent_turns,
)
from apps.documents.models import Document
from services.generation.citation_validator import Citation
from services.generation.generation_service import AnswerResult


def _make_result(answer_text: str = "an answer [CITE:test]", with_citation: bool = True) -> AnswerResult:
    citations = []
    if with_citation:
        chunk_id = uuid.uuid4()
        citations = [
            Citation(
                chunk_id=chunk_id, document_id=uuid.uuid4(), page_number=1,
                section_identifier=None, excerpt="excerpt", confidence_score=0.9,
                retrieval_method="hybrid",
            )
        ]
        answer_text = f"an answer [CITE:{chunk_id}]"
    return AnswerResult(
        query="q", answer_text=answer_text, citations=citations,
        has_valid_citations=with_citation,
        retrieved_chunk_count=1 if with_citation else 0, rejected_citation_count=0,
    )


class ConversationServicesTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.document = Document.objects.create(
            name="Doc", original_filename="d.pdf", file_path="documents/d.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )

    def test_get_or_create_active_session_is_idempotent(self) -> None:
        session_a = get_or_create_active_session(self.document, self.user)
        session_b = get_or_create_active_session(self.document, self.user)
        self.assertEqual(session_a.id, session_b.id)

    def test_sessions_are_isolated_per_document(self) -> None:
        other_document = Document.objects.create(
            name="Other Doc", original_filename="o.pdf", file_path="documents/o.pdf",
            file_size_bytes=1, status=Document.Status.READY,
        )
        session_a = get_or_create_active_session(self.document, self.user)
        session_b = get_or_create_active_session(other_document, self.user)
        self.assertNotEqual(session_a.id, session_b.id)

    @mock.patch("apps.conversation.services.generate_answer")
    def test_ask_in_session_persists_a_turn(self, mock_generate) -> None:
        mock_generate.return_value = _make_result()
        session = get_or_create_active_session(self.document, self.user)

        turn = ask_in_session(session, "what is the tensile strength?")

        self.assertEqual(turn.turn_index, 0)
        self.assertEqual(ConversationTurn.objects.filter(session=session).count(), 1)
        self.assertTrue(turn.has_valid_citations)
        self.assertIn("[1]", turn.answer_text)
        self.assertNotIn("[CITE:", turn.answer_text)

    @mock.patch("apps.conversation.services.generate_answer")
    def test_turn_index_increments_across_calls(self, mock_generate) -> None:
        mock_generate.return_value = _make_result()
        session = get_or_create_active_session(self.document, self.user)

        ask_in_session(session, "first question")
        second_turn = ask_in_session(session, "second question")

        self.assertEqual(second_turn.turn_index, 1)

    @mock.patch("apps.conversation.services.generate_answer")
    def test_ask_in_session_scopes_retrieval_to_this_document_only(self, mock_generate) -> None:
        mock_generate.return_value = _make_result()
        session = get_or_create_active_session(self.document, self.user)

        ask_in_session(session, "a question")

        call_kwargs = mock_generate.call_args.kwargs
        self.assertEqual(call_kwargs["document_ids"], [self.document.id])

    @mock.patch("apps.conversation.services.generate_answer")
    def test_recent_turns_passed_as_prior_context_on_followup(self, mock_generate) -> None:
        mock_generate.return_value = _make_result()
        session = get_or_create_active_session(self.document, self.user)

        ask_in_session(session, "first question")
        mock_generate.reset_mock()
        mock_generate.return_value = _make_result()
        ask_in_session(session, "second question")

        call_kwargs = mock_generate.call_args.kwargs
        self.assertEqual(len(call_kwargs["prior_turns"]), 1)
        self.assertEqual(call_kwargs["prior_turns"][0][0], "first question")

    @mock.patch("apps.conversation.services.generate_answer")
    def test_history_window_caps_at_configured_size(self, mock_generate) -> None:
        mock_generate.return_value = _make_result()
        session = get_or_create_active_session(self.document, self.user)

        with mock.patch("apps.conversation.services._conversation_window_size", return_value=2):
            for i in range(4):
                mock_generate.reset_mock()
                mock_generate.return_value = _make_result()
                ask_in_session(session, f"question {i}")

            recent = get_recent_turns(session)
            self.assertEqual(len(recent), 2)
            self.assertEqual([t.query_text for t in recent], ["question 2", "question 3"])

    @mock.patch("apps.conversation.services.generate_answer")
    def test_clear_session_deactivates_and_starts_fresh(self, mock_generate) -> None:
        mock_generate.return_value = _make_result()
        session = get_or_create_active_session(self.document, self.user)
        ask_in_session(session, "a question")

        new_session = clear_session(session)

        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertNotEqual(new_session.id, session.id)
        self.assertEqual(get_recent_turns(new_session), [])

    @mock.patch("apps.conversation.services.generate_answer")
    def test_old_session_turns_not_visible_after_clear(self, mock_generate) -> None:
        mock_generate.return_value = _make_result()
        session = get_or_create_active_session(self.document, self.user)
        ask_in_session(session, "a question before clearing")

        new_session = clear_session(session)
        next_active = get_or_create_active_session(self.document, self.user)

        self.assertEqual(next_active.id, new_session.id)
        self.assertEqual(ConversationTurn.objects.filter(session=next_active).count(), 0)