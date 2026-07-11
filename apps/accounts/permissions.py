# apps/accounts/permissions.py
"""
SAGE permission constants and role-to-permission mapping.

Permissions are plain string constants, not a database enum. Adding a new
permission requires a code change (intentional — permissions affect security
and should go through review), not a manual database entry.

Default permissions per role are defined here as the single source of truth.
UserProfile.permission_overrides can grant or revoke individual permissions
beyond the role default, but the role definition here drives the baseline.
"""

from __future__ import annotations


class Permission:
    """All application-level permissions in SAGE."""

    # User management
    MANAGE_USERS = "manage_users"
    APPROVE_REGISTRATIONS = "approve_registrations"
    ASSIGN_ROLES = "assign_roles"
    RESET_USER_PASSWORDS = "reset_user_passwords"

    # Audit and system
    VIEW_AUDIT_LOGS = "view_audit_logs"
    CONFIGURE_SYSTEM = "configure_system"

    # Document operations
    UPLOAD_DOCUMENTS = "upload_documents"
    DELETE_DOCUMENTS = "delete_documents"
    MANAGE_DOCUMENTS = "manage_documents"

    # Research operations
    CONDUCT_RESEARCH = "conduct_research"
    EXPORT_DATA = "export_data"

    # Read access
    VIEW_DOCUMENTS = "view_documents"
    VIEW_RESEARCH = "view_research"

    @classmethod
    def all(cls) -> list[str]:
        return [
            v for k, v in vars(cls).items()
            if not k.startswith("_") and isinstance(v, str)
        ]


# Default permission set per role.
# This dict is the authoritative definition — UserProfile.get_permissions()
# starts from here and applies overrides on top.
ROLE_DEFAULT_PERMISSIONS: dict[str, set[str]] = {
    "super_user": set(Permission.all()),

    "system_admin": {
        Permission.MANAGE_USERS,
        Permission.APPROVE_REGISTRATIONS,
        Permission.ASSIGN_ROLES,
        Permission.RESET_USER_PASSWORDS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.CONFIGURE_SYSTEM,
        Permission.UPLOAD_DOCUMENTS,
        Permission.DELETE_DOCUMENTS,
        Permission.MANAGE_DOCUMENTS,
        Permission.CONDUCT_RESEARCH,
        Permission.EXPORT_DATA,
        Permission.VIEW_DOCUMENTS,
        Permission.VIEW_RESEARCH,
    },

    "document_manager": {
        Permission.UPLOAD_DOCUMENTS,
        Permission.DELETE_DOCUMENTS,
        Permission.MANAGE_DOCUMENTS,
        Permission.CONDUCT_RESEARCH,
        Permission.EXPORT_DATA,
        Permission.VIEW_DOCUMENTS,
        Permission.VIEW_RESEARCH,
    },

    "reviewer": {
        Permission.CONDUCT_RESEARCH,
        Permission.EXPORT_DATA,
        Permission.VIEW_DOCUMENTS,
        Permission.VIEW_RESEARCH,
    },

    "engineer": {
        Permission.UPLOAD_DOCUMENTS,
        Permission.CONDUCT_RESEARCH,
        Permission.VIEW_DOCUMENTS,
        Permission.VIEW_RESEARCH,
    },

    "read_only": {
        Permission.VIEW_DOCUMENTS,
        Permission.VIEW_RESEARCH,
    },
}