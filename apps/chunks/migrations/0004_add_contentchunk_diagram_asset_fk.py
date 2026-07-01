# apps/chunks/migrations/0004_add_contentchunk_diagram_asset_fk.py

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chunks", "0003_merge_20260619_1729"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentchunk",
            name="diagram_asset",
            field=models.ForeignKey(
                blank=True,
                help_text="Set only for CAPTION chunks; links back to the source DiagramAsset.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="caption_chunks",
                to="chunks.diagramasset",
            ),
        ),
    ]