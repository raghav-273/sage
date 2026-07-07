# apps/conversation/migrations/0003_add_documentsession_title.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0002_rename_documentsession_identifiers"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentsession",
            name="title",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Human-readable title set when the investigation is started.",
                max_length=255,
            ),
        ),
    ]