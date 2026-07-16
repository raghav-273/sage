# apps/portal/views_admin.py
"""
Administration portal views.

All views are protected with requires_permission — administrators only.
Logic is intentionally kept thin; the AccountRegistration state machine
lives in apps/accounts/models.py and services/audit/.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from services.email.mail_service import send_registration_approved_email
from services.email.mail_service import send_registration_rejected_email

from apps.accounts.decorators import requires_permission
from apps.accounts.models import AccountRegistration, Role, UserProfile
from apps.accounts.permissions import Permission
from services.audit.audit_service import log_event


logger = logging.getLogger("apps.portal.admin")
User = get_user_model()


@requires_permission(Permission.MANAGE_USERS)
def admin_portal(request: HttpRequest) -> HttpResponse:
    """GET /administration/ — administration overview."""
    pending_count = AccountRegistration.objects.filter(
        status=AccountRegistration.Status.PENDING_APPROVAL
    ).count()
    total_users = User.objects.filter(is_active=True).count()
    return render(request, "portal/admin_portal.html", {
        "pending_count": pending_count,
        "total_users": total_users,
    })


@requires_permission(Permission.APPROVE_REGISTRATIONS)
def admin_registrations(request: HttpRequest) -> HttpResponse:
    """GET /administration/registrations/"""
    status_filter = request.GET.get("status", AccountRegistration.Status.PENDING_APPROVAL)
    registrations = AccountRegistration.objects.filter(
        status=status_filter
    ).select_related("reviewed_by").order_by("-submitted_at")

    return render(request, "portal/admin_registrations.html", {
        "registrations": registrations,
        "status_filter": status_filter,
        "status_choices": AccountRegistration.Status.choices,
        "pending_count": AccountRegistration.objects.filter(
            status=AccountRegistration.Status.PENDING_APPROVAL
        ).count(),
    })


@requires_permission(Permission.APPROVE_REGISTRATIONS)
def admin_registration_detail(
    request: HttpRequest, registration_id: str
) -> HttpResponse:
    """GET/POST /administration/registrations/<uuid>/"""
    registration = get_object_or_404(AccountRegistration, id=registration_id)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "approve" and registration.status == AccountRegistration.Status.PENDING_APPROVAL:
            return _approve_registration(request, registration)

        if action == "reject" and registration.status == AccountRegistration.Status.PENDING_APPROVAL:
            reason = request.POST.get("rejection_reason", "").strip()
            if not reason:
                return render(request, "portal/admin_registration_detail.html", {
                    "registration": registration,
                    "error": "A rejection reason is required.",
                })
            return _reject_registration(request, registration, reason)

    return render(request, "portal/admin_registration_detail.html", {
        "registration": registration,
    })


def _approve_registration(
    request: HttpRequest, registration: AccountRegistration
) -> HttpResponse:
    """Creates the User, assigns default role, sends approval email."""
    

    try:
        with transaction.atomic():
            user = User.objects.create(
                username=registration.username,
                email=registration.email,
                first_name=registration.first_name,
                last_name=registration.last_name,
                password=registration.password_hash,
                is_active=True,
            )

            # Assign default engineer role
            try:
                engineer_role = Role.objects.get(name="engineer")
                profile = user.profile
                profile.role = engineer_role
                profile.department = registration.department
                profile.designation = registration.designation
                profile.employee_id = registration.employee_id
                profile.save(update_fields=["role", "department", "designation", "employee_id"])
            except Exception as exc:
                logger.warning("role_assignment_failed user=%s error=%s", user.username, exc)

            registration.status = AccountRegistration.Status.APPROVED
            registration.reviewed_by = request.user
            registration.reviewed_at = timezone.now()
            registration.approved_user = user
            registration.save(update_fields=["status", "reviewed_by", "reviewed_at", "approved_user"])

        log_event(
            event_type="reg_approved",
            actor=request.user,
            target_type="registration",
            target_id=str(registration.id),
            target_label=registration.username,
            request=request,
        )
        log_event(
            event_type="user_created",
            actor=request.user,
            target_type="user",
            target_id=str(user.pk),
            target_label=user.username,
            request=request,
        )

        site_url = getattr(request, "META", {})
        
        login_url = f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/login/"
        send_registration_approved_email(
            recipient=registration.email,
            username=registration.username,
            login_url=login_url,
        )

        logger.info(
            "registration_approved registration_id=%s user_id=%s by=%s",
            registration.id, user.pk, request.user.username,
        )

    except Exception as exc:
        logger.error("registration_approval_failed registration_id=%s error=%s", registration.id, exc)
        return render(request, "portal/admin_registration_detail.html", {
            "registration": registration,
            "error": f"Approval failed: {exc}",
        })

    return redirect("admin-registrations")


def _reject_registration(
    request: HttpRequest, registration: AccountRegistration, reason: str
) -> HttpResponse:
    

    registration.status = AccountRegistration.Status.REJECTED
    registration.reviewed_by = request.user
    registration.reviewed_at = timezone.now()
    registration.rejection_reason = reason
    registration.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])

    log_event(
        event_type="reg_rejected",
        actor=request.user,
        target_type="registration",
        target_id=str(registration.id),
        target_label=registration.username,
        detail={"reason": reason},
        request=request,
    )

    send_registration_rejected_email(
        recipient=registration.email,
        username=registration.username,
        reason=reason,
    )

    return redirect("admin-registrations")