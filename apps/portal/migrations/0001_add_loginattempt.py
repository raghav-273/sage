# apps/portal/migrations/0001_add_loginattempt.py
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="LoginAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip_address", models.GenericIPAddressField()),
                ("username_attempted", models.CharField(blank=True, default="", max_length=255)),
                ("success", models.BooleanField()),
                ("failure_reason", models.CharField(
                    blank=True,
                    choices=[
                        ("bad_credentials", "Bad credentials"),
                        ("turnstile_rejected", "Turnstile rejected"),
                        ("turnstile_absent", "Turnstile token absent"),
                        ("fallback_failed", "Fallback challenge failed"),
                        ("honeypot", "Honeypot triggered"),
                        ("locked_out", "IP locked out"),
                    ],
                    default="",
                    max_length=30,
                )),
                ("user_agent", models.TextField(blank=True, default="")),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.AddIndex(
            model_name="loginattempt",
            index=models.Index(fields=["ip_address", "timestamp"], name="loginattempt_ip_ts_idx"),
        ),
        migrations.AddIndex(
            model_name="loginattempt",
            index=models.Index(fields=["timestamp"], name="loginattempt_ts_idx"),
        ),
    ]