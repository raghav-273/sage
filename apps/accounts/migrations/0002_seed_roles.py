# apps/accounts/migrations/0002_seed_roles.py
"""
Seeds the six predefined system roles.

Data migrations are used instead of fixtures because roles are structural
system data, not optional content. This ensures they exist in every
environment — development, test, and production — from the first migration.
"""

from django.db import migrations


SYSTEM_ROLES = [
    ("super_user", "Super User", "Full system access. Limit to 2-3 designated accounts."),
    ("system_admin", "System Administrator", "User management, approvals, audit access, and system configuration."),
    ("document_manager", "Document Manager", "Document lifecycle management and research access."),
    ("reviewer", "Reviewer", "Research and document access with export rights."),
    ("engineer", "Engineer", "Document upload and research access."),
    ("read_only", "Read Only", "View-only access to documents and research history."),
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for name, display_name, description in SYSTEM_ROLES:
        Role.objects.get_or_create(
            name=name,
            defaults={
                "display_name": display_name,
                "description": description,
                "is_system_role": True,
            },
        )


def reverse_seed_roles(apps, schema_editor):
    # Safe to delete seeded roles only if no UserProfile references them.
    # In practice this migration is not reversed in production.
    Role = apps.get_model("accounts", "Role")
    names = [name for name, _, _ in SYSTEM_ROLES]
    Role.objects.filter(name__in=names, is_system_role=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_seed_roles),
    ]