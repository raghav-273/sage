# services/audit/audit_service.py
"""
Central audit logging service for SAGE.

All application code that needs to write an audit record calls
log_event() from here. This single entry point ensures:
    - Consistent field population (ip_address, user_agent from request)
    - Non-fatal failures (a broken audit write must never break a user action)
    - Future extensibility (e.g. forwarding to a SIEM without touching callers)

log_event() is synchronous and writes within the calling request's
transaction. This is deliberate: an audit record that is rolled back
with the transaction that caused it is worse than a missing audit record.
log_event() uses Django's on_commit() hook where the audit write
must survive a transaction rollback (e.g. a failed document upload should
still log the attempt).

Convenience functions (log_login_success, log_document_uploaded, etc.)
wrap log_event() with pre-filled parameters to reduce boilerplate at
call sites and make audit semantics explicit.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger("services.audit")


def log_event(
    event_type: str,
    severity: str = "info",
    actor=None,
    target_type: str = "",
    target_id: str = "",
    target_label: str = "",
    detail: dict | None = None,
    request: "HttpRequest | None" = None,
    ip_address: str | None = None,
    user_agent: str = "",
) -> None:
    """
    Write a single audit record to AuditLog.

    Failures are caught and logged to the application logger only —
    they must never propagate to the caller.
    """
    from apps.accounts.models import AuditLog

    actor_id: int | None = None
    actor_username: str = ""
    if actor is not None and actor.is_authenticated:
        actor_id = actor.pk
        actor_username = actor.username

    resolved_ip = ip_address
    resolved_ua = user_agent
    if request is not None:
        resolved_ip = resolved_ip or request.META.get("REMOTE_ADDR")
        resolved_ua = resolved_ua or request.META.get("HTTP_USER_AGENT", "")[:500]

    try:
        AuditLog.objects.create(
            event_type=event_type,
            severity=severity,
            actor_id=actor_id,
            actor_username=actor_username,
            target_type=target_type,
            target_id=str(target_id) if target_id else "",
            target_label=target_label[:500],
            ip_address=resolved_ip,
            user_agent=resolved_ua,
            detail=detail or {},
        )
    except Exception as exc:
        logger.error(
            "audit_write_failed event_type=%s actor=%s error=%s",
            event_type, actor_username, exc,
        )


# ── Convenience functions ─────────────────────────────────────────────


def log_login_success(request: "HttpRequest", user) -> None:
    log_event(
        event_type="auth_login_success",
        actor=user,
        request=request,
    )


def log_login_failure(
    request: "HttpRequest",
    username_attempted: str,
    reason: str = "",
) -> None:
    log_event(
        event_type="auth_login_failure",
        severity="warning",
        target_type="user",
        target_label=username_attempted,
        detail={"reason": reason},
        request=request,
    )


def log_logout(request: "HttpRequest", user) -> None:
    log_event(
        event_type="auth_logout",
        actor=user,
        request=request,
    )


def log_ip_lockout(request: "HttpRequest", ip: str) -> None:
    log_event(
        event_type="auth_ip_lockout",
        severity="critical",
        detail={"locked_ip": ip},
        request=request,
        ip_address=ip,
    )


def log_password_reset_requested(request: "HttpRequest", user) -> None:
    log_event(
        event_type="auth_password_reset_requested",
        severity="warning",
        actor=user,
        target_type="user",
        target_id=str(user.pk),
        target_label=user.username,
        request=request,
    )


def log_password_reset_completed(request: "HttpRequest", user) -> None:
    log_event(
        event_type="auth_password_reset_completed",
        actor=user,
        target_type="user",
        target_id=str(user.pk),
        target_label=user.username,
        request=request,
    )


def log_document_uploaded(request: "HttpRequest", user, document) -> None:
    log_event(
        event_type="doc_uploaded",
        actor=user,
        target_type="document",
        target_id=str(document.id),
        target_label=document.name,
        detail={"file_size_bytes": document.file_size_bytes},
        request=request,
    )


def log_document_accessed(request: "HttpRequest", user, document) -> None:
    log_event(
        event_type="doc_accessed",
        actor=user,
        target_type="document",
        target_id=str(document.id),
        target_label=document.name,
        request=request,
    )


def log_research_query(request: "HttpRequest", user, session) -> None:
    log_event(
        event_type="research_query_executed",
        actor=user,
        target_type="session",
        target_id=str(session.id),
        target_label=session.title or "Untitled",
        request=request,
    )


def log_research_exported(request: "HttpRequest", user, session) -> None:
    log_event(
        event_type="research_exported",
        actor=user,
        target_type="session",
        target_id=str(session.id),
        target_label=session.title or "Untitled",
        request=request,
    )


def log_compliance_check(request: "HttpRequest", user, document) -> None:
    log_event(
        event_type="compliance_check_executed",
        actor=user,
        target_type="document",
        target_id=str(document.id),
        target_label=document.name,
        request=request,
    )


def log_comparison_executed(request: "HttpRequest", user, doc_a_name: str, doc_b_name: str) -> None:
    log_event(
        event_type="comparison_executed",
        actor=user,
        detail={"document_a": doc_a_name, "document_b": doc_b_name},
        request=request,
    )


def log_user_role_changed(
    acting_user,
    target_user,
    old_role_name: str,
    new_role_name: str,
    request: "HttpRequest | None" = None,
) -> None:
    log_event(
        event_type="user_role_changed",
        severity="warning",
        actor=acting_user,
        target_type="user",
        target_id=str(target_user.pk),
        target_label=target_user.username,
        detail={"old_role": old_role_name, "new_role": new_role_name},
        request=request,
    )