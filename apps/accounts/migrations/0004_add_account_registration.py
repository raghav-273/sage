# apps/accounts/migrations/0004_add_account_registration.py
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0003_assign_default_roles"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountRegistration",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(db_index=True)),
                ("username", models.CharField(max_length=150)),
                ("first_name", models.CharField(blank=True, default="", max_length=150)),
                ("last_name", models.CharField(blank=True, default="", max_length=150)),
                ("department", models.CharField(blank=True, default="", max_length=255)),
                ("designation", models.CharField(blank=True, default="", max_length=255)),
                ("employee_id", models.CharField(blank=True, default="", max_length=100)),
                ("reason_for_access", models.TextField(help_text="Why the applicant requires access to SAGE.")),
                ("password_hash", models.CharField(max_length=128, help_text="Django password hash. Set on registration; applied to the User on approval.")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_verification", "Pending Email Verification"),
                            ("pending_approval", "Pending Approval"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="pending_verification",
                        max_length=25,
                    ),
                ),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True, default="")),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_user",
                    models.OneToOneField(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="registration",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_registrations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-submitted_at"]},
        ),
        migrations.AddIndex(
            model_name="accountregistration",
            index=models.Index(fields=["status", "submitted_at"], name="accreg_status_ts_idx"),
        ),
    ]