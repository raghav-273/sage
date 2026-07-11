# apps/accounts/migrations/0001_initial.py

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=50, unique=True)),
                ("display_name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True, default="")),
                ("is_system_role", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("permission_overrides", models.JSONField(blank=True, default=dict)),
                ("department", models.CharField(blank=True, default="", max_length=255)),
                ("designation", models.CharField(blank=True, default="", max_length=255)),
                ("employee_id", models.CharField(blank=True, default="", max_length=100)),
                ("phone_number", models.CharField(blank=True, default="", max_length=30)),
                ("requires_password_reset", models.BooleanField(default=False)),
                ("last_activity_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="profiles",
                        to="accounts.role",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(
                    choices=[
                        ("auth_login_success", "Login — Success"),
                        ("auth_login_failure", "Login — Failure"),
                        ("auth_logout", "Logout"),
                        ("auth_password_reset_requested", "Password Reset — Requested"),
                        ("auth_password_reset_completed", "Password Reset — Completed"),
                        ("auth_ip_lockout", "IP Lockout Triggered"),
                        ("reg_submitted", "Registration — Submitted"),
                        ("reg_email_verified", "Registration — Email Verified"),
                        ("reg_approved", "Registration — Approved"),
                        ("reg_rejected", "Registration — Rejected"),
                        ("user_created", "User — Created"),
                        ("user_role_changed", "User — Role Changed"),
                        ("user_permission_overridden", "User — Permission Override"),
                        ("user_deactivated", "User — Deactivated"),
                        ("user_reactivated", "User — Reactivated"),
                        ("user_password_admin_reset", "User — Admin Password Reset"),
                        ("doc_uploaded", "Document — Uploaded"),
                        ("doc_deleted", "Document — Deleted"),
                        ("doc_ingestion_completed", "Document — Ingestion Completed"),
                        ("doc_ingestion_failed", "Document — Ingestion Failed"),
                        ("doc_accessed", "Document — Accessed"),
                        ("research_session_started", "Research — Session Started"),
                        ("research_query_executed", "Research — Query Executed"),
                        ("research_exported", "Research — Exported"),
                        ("compliance_check_executed", "Compliance — Check Executed"),
                        ("comparison_executed", "Comparison — Executed"),
                        ("system_config_changed", "System — Config Changed"),
                    ],
                    db_index=True,
                    max_length=60,
                )),
                ("severity", models.CharField(
                    choices=[("info", "Info"), ("warning", "Warning"), ("critical", "Critical")],
                    db_index=True,
                    default="info",
                    max_length=10,
                )),
                ("actor_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("actor_username", models.CharField(blank=True, default="", max_length=150)),
                ("target_type", models.CharField(blank=True, default="", max_length=50)),
                ("target_id", models.CharField(blank=True, default="", max_length=100)),
                ("target_label", models.CharField(blank=True, default="", max_length=500)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["event_type", "timestamp"], name="auditlog_event_ts_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["actor_id", "timestamp"], name="auditlog_actor_ts_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["severity", "timestamp"], name="auditlog_severity_ts_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["target_type", "target_id"], name="auditlog_target_idx"),
        ),
    ]