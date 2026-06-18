# config/__init__.py
#
# Importing the Celery app here ensures it is initialised when Django starts.
# This is required for @shared_task decorators in apps/*/tasks.py to register
# correctly with the Celery worker.
#
# Reference: https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html

from .celery import app as celery_app

__all__ = ("celery_app",)