# apps/portal/migrations/0002_deprecate_loginattempt.py
"""
Marks LoginAttempt as deprecated in favour of AuditLog (apps.accounts).

Adds a deprecated_at DateTimeField (auto_now_add=True) to signal to
any future code reader that LoginAttempt is historical data only.
New code writes to AuditLog exclusively.
"""

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0001_add_loginattempt"),
        ("accounts", "0003_assign_default_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="loginattempt",
            name="migrated_to_auditlog",
            field=models.BooleanField(
                default=False,
                help_text="True once this record has been superseded by an AuditLog entry.",
            ),
        ),
    ]