# config/celery.py

import os
from celery import Celery

# Set the default Django settings module for the Celery command-line program
# and for any worker processes that start without an explicit DJANGO_SETTINGS_MODULE.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# The application name ('sage') appears as a prefix in all task names.
# Example: sage.apps.ingestion.tasks.process_document
app = Celery("sage")

# Load Celery configuration from Django settings.
# All keys prefixed with CELERY_ are passed to Celery (prefix is stripped).
# CELERY_BROKER_URL → BROKER_URL, CELERY_TASK_SERIALIZER → TASK_SERIALIZER, etc.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Automatically discover tasks in apps/*/tasks.py files.
# Any installed app that contains a tasks.py module is scanned.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """
    Diagnostic task that confirms the Celery worker is operational.

    Run with:
        docker compose exec web celery -A sage call sage.debug_task
    """
    print(f"Worker received debug_task. Request: {self.request!r}")