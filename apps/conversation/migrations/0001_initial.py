# apps/conversation/migrations/0001_initial.py

import uuid

import django.db.models.deletion
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("documents", "0002_alter_document_error_message_alter_document_name_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True, help_text="False once cleared. Clearing creates a fresh session rather than mutating this one — old history stays available for audit, just inactive.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversation_sessions",
                        to="documents.document",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversation_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ConversationTurn",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("turn_index", models.PositiveIntegerField(help_text="0-based, monotonically increasing per session.")),
                ("query_text", models.TextField()),
                ("answer_text", models.TextField(help_text="Already rendered — [CITE:id] markers replaced before storage.")),
                ("has_valid_citations", models.BooleanField(default=False)),
                ("retrieved_chunk_count", models.PositiveIntegerField(default=0)),
                ("citations", models.JSONField(blank=True, default=list, encoder=DjangoJSONEncoder, help_text="Serialized Citation dataclasses at the time of this turn.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="turns",
                        to="conversation.documentsession",
                    ),
                ),
            ],
            options={"ordering": ["session", "turn_index"]},
        ),
        migrations.AddIndex(
            model_name="documentsession",
            index=models.Index(fields=["document", "user", "is_active"], name="conv_doc_user_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="documentsession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("document", "user"),
                name="uniq_active_doc_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="conversationturn",
            constraint=models.UniqueConstraint(
                fields=("session", "turn_index"), name="uniq_session_turn_index"
            ),
        ),
    ]