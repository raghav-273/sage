# apps/portal/health.py
"""
Lightweight system health checks for the dashboard — direct connectivity
probes, not a monitoring framework. No caching, no historical metrics.
Designed conceptually during Milestone 9A planning; implemented now that
the dashboard page that displays it exists.
"""

from __future__ import annotations

from dataclasses import dataclass

import redis
from django.conf import settings
from django.db import connection


@dataclass
class HealthStatus:
    name: str
    healthy: bool
    detail: str = ""


def check_postgres() -> HealthStatus:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return HealthStatus(name="PostgreSQL", healthy=True)
    except Exception as exc:
        return HealthStatus(name="PostgreSQL", healthy=False, detail=str(exc))


def check_redis() -> HealthStatus:
    try:
        client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL, socket_connect_timeout=1.0, socket_timeout=1.0
        )
        client.ping()
        return HealthStatus(name="Redis", healthy=True)
    except Exception as exc:
        return HealthStatus(name="Redis", healthy=False, detail=str(exc))


def check_celery_worker() -> HealthStatus:
    try:
        from config.celery import app

        # Explicit 1-second timeout is the detail that actually matters:
        # without it, inspect().ping() can take several seconds to give up
        # when no worker is running, visibly stalling every dashboard load.
        replies = app.control.inspect(timeout=1.0).ping()
        if replies:
            return HealthStatus(
                name="Celery Worker", healthy=True, detail=f"{len(replies)} worker(s) responding"
            )
        return HealthStatus(name="Celery Worker", healthy=False, detail="No workers responded")
    except Exception as exc:
        return HealthStatus(name="Celery Worker", healthy=False, detail=str(exc))


def get_system_health() -> list[HealthStatus]:
    return [check_postgres(), check_redis(), check_celery_worker()]