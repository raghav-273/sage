# apps/conversation/models.py
"""
DocumentSession — one conversation, scoped to exactly one Document.
This is what makes "no leakage across documents" true by construction:
ConversationTurn has no document link of its own, only via session, so
there is no way to attach a turn to more than one document.

ConversationTurn — one query+answer pair within a session.
"""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.documents.models import Document


class DocumentSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="conversation_sessions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversation_sessions"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="False once cleared. Clearing creates a fresh session rather than "
                   "mutating this one — old history stays available for audit, just inactive.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["document", "user", "is_active"], name="conv_doc_user_active_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "user"],
                condition=models.Q(is_active=True),
                name="uniq_active_doc_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document.name} — {self.user.username} ({'active' if self.is_active else 'closed'})"


class ConversationTurn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(DocumentSession, on_delete=models.CASCADE, related_name="turns")
    turn_index = models.PositiveIntegerField(help_text="0-based, monotonically increasing per session.")
    query_text = models.TextField()
    answer_text = models.TextField(help_text="Already rendered — [CITE:id] markers replaced before storage.")
    has_valid_citations = models.BooleanField(default=False)
    retrieved_chunk_count = models.PositiveIntegerField(default=0)
    citations = models.JSONField(
        default=list, blank=True, encoder=DjangoJSONEncoder,
        help_text="Serialized Citation dataclasses at the time of this turn.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["session", "turn_index"]
        constraints = [
            models.UniqueConstraint(fields=["session", "turn_index"], name="uniq_session_turn_index"),
        ]

    def __str__(self) -> str:
        return f"Turn {self.turn_index} — {self.query_text[:50]}"