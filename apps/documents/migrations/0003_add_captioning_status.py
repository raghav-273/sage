# apps/documents/migrations/0003_add_captioning_status.py
#
# Adds CAPTIONING to Document.Status choices.
# PostgreSQL stores this column as a plain VARCHAR — adding a new choice
# value requires no actual DDL; this migration only updates Django's
# migration state so makemigrations --check stays clean.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0002_alter_document_error_message_alter_document_name_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("QUEUED", "Queued"),
                    ("EXTRACTING", "Extracting"),
                    ("CHUNKING", "Chunking"),
                    ("CAPTIONING", "Captioning"),
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
    ]