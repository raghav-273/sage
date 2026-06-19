# apps/documents/migrations/0001_initial.py

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("original_filename", models.CharField(max_length=255)),
                ("file_path", models.CharField(max_length=500)),
                ("file_size_bytes", models.BigIntegerField()),
                ("mime_type", models.CharField(default="application/pdf", max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("QUEUED", "Queued"),
                            ("EXTRACTING", "Extracting"),
                            ("CHUNKING", "Chunking"),
                            ("EMBEDDING", "Embedding"),
                            ("GRAPHING", "Graphing"),
                            ("READY", "Ready"),
                            ("FAILED", "Failed"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("page_count", models.PositiveIntegerField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DocumentPage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("page_number", models.PositiveIntegerField()),
                ("raw_text", models.TextField(blank=True, default="")),
                ("has_images", models.BooleanField(default=False)),
                ("has_tables", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pages",
                        to="documents.document",
                    ),
                ),
            ],
            options={"ordering": ["page_number"]},
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["status"], name="doc_status_idx"),
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["-created_at"], name="doc_created_idx"),
        ),
        migrations.AddConstraint(
            model_name="documentpage",
            constraint=models.UniqueConstraint(
                fields=("document", "page_number"),
                name="uniq_document_page_number",
            ),
        ),
    ]