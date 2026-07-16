# apps/accounts/models.py
"""
UserProfile and Role models for SAGE RBAC.

Design rationale:
    Django's built-in User model handles authentication. UserProfile extends
    it with role, permission overrides, and organisational metadata via a
    OneToOneField. This avoids replacing Django's auth machinery while
    adding application-level access control on top of it.

    AuditLog lives here rather than in apps.portal because it is a
    cross-cutting identity and access concern, not a portal UI concern.
    apps.portal imports from apps.accounts, not the reverse.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


from .permissions import ROLE_DEFAULT_PERMISSIONS, Permission


class Role(models.Model):
    """
    A named role with a defined default permission set.

    Predefined roles are seeded by a data migration. The name field
    corresponds to a key in ROLE_DEFAULT_PERMISSIONS; custom roles added
    by administrators default to the read_only permission set.
    """

    class RoleName(models.TextChoices):
        SUPER_USER = "super_user", "Super User"
        SYSTEM_ADMIN = "system_admin", "System Administrator"
        DOCUMENT_MANAGER = "document_manager", "Document Manager"
        REVIEWER = "reviewer", "Reviewer"
        ENGINEER = "engineer", "Engineer"
        READ_ONLY = "read_only", "Read Only"

    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_system_role = models.BooleanField(
        default=True,
        help_text="System roles cannot be deleted; only custom roles can.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.display_name

    def default_permissions(self) -> set[str]:
        return ROLE_DEFAULT_PERMISSIONS.get(self.name, ROLE_DEFAULT_PERMISSIONS["read_only"])


class UserProfile(models.Model):
    """
    Extends Django's User with SAGE-specific role, permissions, and metadata.

    permission_overrides is a JSON object with two optional keys:
        "grant":  list[str] — permissions beyond the role default
        "revoke": list[str] — permissions removed from the role default

    This structure allows per-user customisation without creating a
    many-to-many permission table.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="profiles",
        null=True,
        blank=True,
        help_text="Null until a role is explicitly assigned (treated as read_only).",
    )
    permission_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"grant": ["permission_name"], "revoke": ["permission_name"]}',
    )

    # Organisational metadata — useful for government/enterprise context
    department = models.CharField(max_length=255, blank=True, default="")
    designation = models.CharField(max_length=255, blank=True, default="")
    employee_id = models.CharField(max_length=100, blank=True, default="")
    phone_number = models.CharField(max_length=30, blank=True, default="")

    # Account lifecycle
    requires_password_reset = models.BooleanField(
        default=False,
        help_text="Set True by administrators to force a password change on next login.",
    )
    last_activity_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.username} ({self.role or 'no role'})"

    def get_permissions(self) -> set[str]:
        """
        Computes the full effective permission set for this user.

        Precedence: role defaults → grants applied → revocations applied.
        Staff and superuser flags in Django's User bypass this check in
        has_permission() below — they always have full access, by design,
        to allow emergency administrative access without role configuration.
        """
        if self.role:
            base = set(self.role.default_permissions())
        else:
            base = set(ROLE_DEFAULT_PERMISSIONS["read_only"])

        grants = set(self.permission_overrides.get("grant", []))
        revocations = set(self.permission_overrides.get("revoke", []))

        return (base | grants) - revocations

    def has_permission(self, permission: str) -> bool:
        """
        Returns True if this user has the named permission.

        Django staff and superusers bypass RBAC and always return True,
        so the Django admin and emergency management tools are never blocked
        by application-level permissions.
        """
        if self.user.is_superuser or self.user.is_staff:
            return True
        return permission in self.get_permissions()


class AccountRegistration(models.Model):
    """
    Pre-approval registration record.

    A User row is NOT created until an administrator approves the registration.
    This prevents partially-created users from interacting with the permission
    system during the review period.

    Password is stored as a Django-hashed value (make_password()) so the
    applicant's chosen password is preserved through approval without
    being stored in plain text. On approval, the User is created with
    this hash already set.

    Email verification uses django.core.signing.TimestampSigner with the
    registration UUID as the signed value — no token table required.
    The token is valid for REGISTRATION_VERIFICATION_TIMEOUT_SECONDS
    (default 48 hours).
    """

    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Pending Email Verification"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Applicant details
    email = models.EmailField(db_index=True)
    username = models.CharField(max_length=150)
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
    department = models.CharField(max_length=255, blank=True, default="")
    designation = models.CharField(max_length=255, blank=True, default="")
    employee_id = models.CharField(max_length=100, blank=True, default="")
    reason_for_access = models.TextField(
        help_text="Why the applicant requires access to SAGE."
    )
    password_hash = models.CharField(
        max_length=128,
        help_text="Django password hash. Set on registration; applied to the User on approval.",
    )

    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING_VERIFICATION,
        db_index=True,
    )

    # Email verification
    verified_at = models.DateTimeField(null=True, blank=True)

    # Administrator review
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_registrations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    # Linked User (set on approval)
    approved_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="registration",
    )

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["status", "submitted_at"], name="accreg_status_ts_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.username} <{self.email}> [{self.status}]"

    def make_verification_token(self) -> str:
        """Returns a signed, expiring token for email verification."""
        from django.core.signing import TimestampSigner
        signer = TimestampSigner(salt="apps.accounts.registration.verify")
        return signer.sign(str(self.id))

    @classmethod
    def verify_token(cls, token: str, max_age_seconds: int = 172800) -> "AccountRegistration | None":
        """
        Validates a verification token and returns the registration, or None
        if the token is invalid or expired.
        """
        from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
        signer = TimestampSigner(salt="apps.accounts.registration.verify")
        try:
            registration_id = signer.unsign(token, max_age=max_age_seconds)
            return cls.objects.get(id=registration_id, status=cls.Status.PENDING_VERIFICATION)
        except (BadSignature, SignatureExpired, cls.DoesNotExist):
            return None

class AuditLog(models.Model):
    """
    Unified audit record for all security- and compliance-relevant events.

    A single model with an event_type enum is preferred over per-category
    models because real investigations span event types. Separate models
    would require cross-table unions to audit "everything that happened to
    this document" or "everything this user did in a 30-minute window".

    LoginAttempt (apps.portal) remains but is deprecated — new code writes
    here. LoginAttempt rows remain queryable for historical data.
    """

    class EventType(models.TextChoices):
        # Authentication
        AUTH_LOGIN_SUCCESS = "auth_login_success", "Login — Success"
        AUTH_LOGIN_FAILURE = "auth_login_failure", "Login — Failure"
        AUTH_LOGOUT = "auth_logout", "Logout"
        AUTH_PASSWORD_RESET_REQUESTED = "auth_password_reset_requested", "Password Reset — Requested"
        AUTH_PASSWORD_RESET_COMPLETED = "auth_password_reset_completed", "Password Reset — Completed"
        AUTH_IP_LOCKOUT = "auth_ip_lockout", "IP Lockout Triggered"

        # Registration
        REG_SUBMITTED = "reg_submitted", "Registration — Submitted"
        REG_EMAIL_VERIFIED = "reg_email_verified", "Registration — Email Verified"
        REG_APPROVED = "reg_approved", "Registration — Approved"
        REG_REJECTED = "reg_rejected", "Registration — Rejected"

        # User management
        USER_CREATED = "user_created", "User — Created"
        USER_ROLE_CHANGED = "user_role_changed", "User — Role Changed"
        USER_PERMISSION_OVERRIDDEN = "user_permission_overridden", "User — Permission Override"
        USER_DEACTIVATED = "user_deactivated", "User — Deactivated"
        USER_REACTIVATED = "user_reactivated", "User — Reactivated"
        USER_PASSWORD_ADMIN_RESET = "user_password_admin_reset", "User — Admin Password Reset"

        # Document operations
        DOC_UPLOADED = "doc_uploaded", "Document — Uploaded"
        DOC_DELETED = "doc_deleted", "Document — Deleted"
        DOC_INGESTION_COMPLETED = "doc_ingestion_completed", "Document — Ingestion Completed"
        DOC_INGESTION_FAILED = "doc_ingestion_failed", "Document — Ingestion Failed"
        DOC_ACCESSED = "doc_accessed", "Document — Accessed"

        # Research
        RESEARCH_SESSION_STARTED = "research_session_started", "Research — Session Started"
        RESEARCH_QUERY_EXECUTED = "research_query_executed", "Research — Query Executed"
        RESEARCH_EXPORTED = "research_exported", "Research — Exported"
        COMPLIANCE_CHECK_EXECUTED = "compliance_check_executed", "Compliance — Check Executed"
        COMPARISON_EXECUTED = "comparison_executed", "Comparison — Executed"

        # System
        SYSTEM_CONFIG_CHANGED = "system_config_changed", "System — Config Changed"

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=60, choices=EventType.choices, db_index=True)
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.INFO, db_index=True
    )

    # Actor — who performed the action.
    # actor_id is nullable for pre-authentication events (login failures
    # before a user is identified). actor_username is denormalised so
    # audit records remain meaningful if the user account is later deleted.
    actor_id = models.IntegerField(null=True, blank=True, db_index=True)
    actor_username = models.CharField(max_length=150, blank=True, default="")

    # Target — what the action was performed on.
    target_type = models.CharField(
        max_length=50, blank=True, default="",
        help_text="e.g. 'document', 'user', 'session'",
    )
    target_id = models.CharField(max_length=100, blank=True, default="")
    target_label = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Human-readable name of the target, denormalised.",
    )

    # Request context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    # Event-specific structured data — failure reason, old/new values, etc.
    detail = models.JSONField(default=dict, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["event_type", "timestamp"], name="auditlog_event_ts_idx"),
            models.Index(fields=["actor_id", "timestamp"], name="auditlog_actor_ts_idx"),
            models.Index(fields=["severity", "timestamp"], name="auditlog_severity_ts_idx"),
            models.Index(fields=["target_type", "target_id"], name="auditlog_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} — {self.actor_username or 'anonymous'} — {self.timestamp:%Y-%m-%d %H:%M:%S}"