# apps/chunks/migrations/0001_initial.py

import uuid

import django.db.models.deletion
import pgvector.django
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("documents", "0001_initial"),
    ]

    operations = [
        # Ensures the pgvector type is registered in this database.
        # Required even though infrastructure/postgres/init.sql already ran
        # CREATE EXTENSION on the dev database — Django's test database is
        # created fresh and does not execute init.sql.
        pgvector.django.VectorExtension(),

        migrations.CreateModel(
            name="ContentChunk",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("chunk_index", models.PositiveIntegerField()),
                ("chunk_text", models.TextField()),
                (
                    "chunk_type",
                    models.CharField(
                        choices=[
                            ("text", "Text"),
                            ("table", "Table"),
                            ("caption", "Caption"),
                            ("heading", "Heading"),
                        ],
                        default="text",
                        max_length=20,
                    ),
                ),
                ("section_identifier", models.CharField(blank=True, max_length=255, null=True)),
                ("token_count", models.PositiveIntegerField(default=0)),
                ("embedding", pgvector.django.VectorField(blank=True, dimensions=1536, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="documents.document",
                    ),
                ),
                (
                    "page",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="documents.documentpage",
                    ),
                ),
            ],
            options={"ordering": ["document", "chunk_index"]},
        ),
        migrations.CreateModel(
            name="DiagramAsset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("image_path", models.CharField(max_length=500)),
                ("image_format", models.CharField(default="PNG", max_length=20)),
                ("width_px", models.PositiveIntegerField(blank=True, null=True)),
                ("height_px", models.PositiveIntegerField(blank=True, null=True)),
                ("caption", models.TextField(blank=True, null=True)),
                ("ocr_text", models.TextField(blank=True, null=True)),
                ("bounding_box", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="diagrams",
                        to="documents.document",
                    ),
                ),
                (
                    "page",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="diagrams",
                        to="documents.documentpage",
                    ),
                ),
            ],
            options={"ordering": ["document", "page"]},
        ),
        migrations.AddIndex(
            model_name="contentchunk",
            index=models.Index(fields=["section_identifier"], name="chunk_section_idx"),
        ),
        migrations.AddConstraint(
            model_name="contentchunk",
            constraint=models.UniqueConstraint(
                fields=("document", "chunk_index"),
                name="uniq_document_chunk_index",
            ),
        ),
        migrations.AddIndex(
            model_name="diagramasset",
            index=models.Index(fields=["document"], name="diagram_document_idx"),
        ),
    ]