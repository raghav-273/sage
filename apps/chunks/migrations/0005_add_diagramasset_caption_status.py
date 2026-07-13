# apps/chunks/migrations/0005_add_diagramasset_caption_status.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chunks", "0004_add_contentchunk_diagram_asset_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="diagramasset",
            name="caption_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("in_progress", "In Progress"),
                    ("complete", "Complete"),
                    ("failed", "Failed"),
                    ("skipped", "Skipped — no useful content"),
                ],
                default="pending",
                max_length=15,
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name="diagramasset",
            name="caption_error",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Last error message from caption generation, if any.",
            ),
        ),
        migrations.AddField(
            model_name="diagramasset",
            name="caption_attempts",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Number of caption generation attempts made.",
            ),
        ),
    ]