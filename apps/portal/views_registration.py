# apps/portal/views_registration.py
"""
Registration workflow views.

Separated from views.py to keep the registration state machine logic
isolated and testable. No RBAC check needed — registration is public.
"""

from __future__ import annotations

import logging

from services.email.mail_service import (
    send_admin_new_registration_notification,
    send_registration_pending_email,
    send_registration_verification_email,
)
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import AccountRegistration , Role
from services.audit.audit_service import log_event

logger = logging.getLogger("apps.portal.registration")

User = get_user_model()


def _get_admin_emails() -> list[str]:
    """
    Returns email addresses of all active system admins and super users.
    Falls back to ADMINS setting if no RBAC users with those roles exist yet.
    """
    
    try:
        admin_roles = Role.objects.filter(name__in=["super_user", "system_admin"])
        emails = list(
            User.objects.filter(
                profile__role__in=admin_roles,
                is_active=True,
                email__isnull=False,
            ).exclude(email="")
            .values_list("email", flat=True)
        )
        if emails:
            return emails
    except Exception:
        pass
    return [email for _, email in getattr(settings, "ADMINS", [])]


def _validate_registration_form(post_data: dict) -> tuple[dict, list[str]]:
    """
    Validates registration form data.
    Returns (cleaned_data, error_list). errors is empty on success.
    """
    errors: list[str] = []
    cleaned: dict = {}

    required_fields = {
        "username": "Username",
        "email": "Email address",
        "password": "Password",
        "password_confirm": "Password confirmation",
        "reason_for_access": "Reason for access",
    }

    for field, label in required_fields.items():
        value = post_data.get(field, "").strip()
        if not value:
            errors.append(f"{label} is required.")
        else:
            cleaned[field] = value

    if errors:
        return cleaned, errors

    # Username validation
    username = cleaned["username"]
    if len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    elif not username.replace("_", "").replace("-", "").isalnum():
        errors.append("Username may only contain letters, numbers, hyphens, and underscores.")
    elif User.objects.filter(username__iexact=username).exists():
        errors.append("This username is already taken.")
    elif AccountRegistration.objects.filter(
        username__iexact=username,
        status__in=[
            AccountRegistration.Status.PENDING_VERIFICATION,
            AccountRegistration.Status.PENDING_APPROVAL,
        ],
    ).exists():
        errors.append("A registration with this username is already pending.")

    # Email validation
    email = cleaned["email"]
    try:
        validate_email(email)
    except ValidationError:
        errors.append("Please enter a valid email address.")
    else:
        if User.objects.filter(email__iexact=email).exists():
            errors.append("An account with this email address already exists.")
        elif AccountRegistration.objects.filter(
            email__iexact=email,
            status__in=[
                AccountRegistration.Status.PENDING_VERIFICATION,
                AccountRegistration.Status.PENDING_APPROVAL,
            ],
        ).exists():
            errors.append("A registration with this email address is already pending.")

    # Password validation
    password = cleaned.get("password", "")
    password_confirm = cleaned.get("password_confirm", "")
    if password and password_confirm:
        if password != password_confirm:
            errors.append("Passwords do not match.")
        elif len(password) < 10:
            errors.append("Password must be at least 10 characters.")

    for optional in ["first_name", "last_name", "department", "designation", "employee_id"]:
        cleaned[optional] = post_data.get(optional, "").strip()

    return cleaned, errors


def registration_page(request: HttpRequest) -> HttpResponse:
    """GET/POST /register/"""
    if request.user.is_authenticated:
        return redirect("dashboard")

    errors: list[str] = []
    form_data: dict = {}

    if request.method == "POST":
        form_data = dict(request.POST)
        cleaned, errors = _validate_registration_form(request.POST)

        if not errors:
            registration = AccountRegistration.objects.create(
                email=cleaned["email"].lower(),
                username=cleaned["username"],
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
                department=cleaned.get("department", ""),
                designation=cleaned.get("designation", ""),
                employee_id=cleaned.get("employee_id", ""),
                reason_for_access=cleaned["reason_for_access"],
                password_hash=make_password(cleaned["password"]),
            )

            # Build verification URL and send email
            token = registration.make_verification_token()
            site_url = getattr(settings, "SITE_URL", "http://localhost:8000")
            verification_url = f"{site_url}/register/verify/{token}/"

            sent = send_registration_verification_email(
                recipient=registration.email,
                username=registration.username,
                verification_url=verification_url,
            )
            if not sent:
                logger.error(
                    "registration_verification_email_failed registration_id=%s",
                    registration.id,
                )

            log_event(
                event_type="reg_submitted",
                target_type="registration",
                target_id=str(registration.id),
                target_label=registration.username,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            return redirect("registration-done")

    return render(request, "portal/register.html", {
        "errors": errors,
        "form_data": form_data,
    })


def registration_done(request: HttpRequest) -> HttpResponse:
    """GET /register/done/ — shown after successful form submission."""
    return render(request, "portal/register_done.html")


def registration_verify(request: HttpRequest, token: str) -> HttpResponse:
    """GET /register/verify/<token>/"""
    timeout = getattr(settings, "REGISTRATION_VERIFICATION_TIMEOUT_SECONDS", 172800)
    registration = AccountRegistration.verify_token(token, max_age_seconds=timeout)

    if registration is None:
        return render(request, "portal/register_verify.html", {
            "valid": False,
        })

    # Advance state
    registration.status = AccountRegistration.Status.PENDING_APPROVAL
    registration.verified_at = timezone.now()
    registration.save(update_fields=["status", "verified_at"])

    log_event(
        event_type="reg_email_verified",
        target_type="registration",
        target_id=str(registration.id),
        target_label=registration.username,
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    # Notify the user that review is pending
    send_registration_pending_email(
        recipient=registration.email,
        username=registration.username,
    )

    # Notify administrators
    site_url = getattr(settings, "SITE_URL", "http://localhost:8000")
    review_url = f"{site_url}/administration/registrations/{registration.id}/"

    for admin_email in _get_admin_emails():
        send_admin_new_registration_notification(
            admin_email=admin_email,
            applicant_username=registration.username,
            review_url=review_url,
        )

    return render(request, "portal/register_verify.html", {
        "valid": True,
        "username": registration.username,
    })