# apps/accounts/migrations/0003_assign_default_roles.py
"""
Assigns default roles to existing users.

    - Django staff (is_staff=True): System Administrator
    - Django superusers (is_superuser=True): Super User
    - All others: Engineer

Profiles are created for any user that doesn't have one yet — possible
for users created before this app existed (e.g. the initial superuser
created via createsuperuser before apps.accounts was installed).
"""

from django.db import migrations


def assign_default_roles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")
    Role = apps.get_model("accounts", "Role")

    try:
        super_user_role = Role.objects.get(name="super_user")
        system_admin_role = Role.objects.get(name="system_admin")
        engineer_role = Role.objects.get(name="engineer")
    except Role.DoesNotExist:
        # Roles not seeded yet — dependency ordering should prevent this.
        return

    for user in User.objects.all():
        profile, _ = UserProfile.objects.get_or_create(user=user)

        if profile.role_id is not None:
            continue  # already has a role; don't overwrite

        if user.is_superuser:
            profile.role = super_user_role
        elif user.is_staff:
            profile.role = system_admin_role
        else:
            profile.role = engineer_role

        profile.save(update_fields=["role"])


def reverse_assign_default_roles(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserProfile.objects.all().update(role=None)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_seed_roles"),
    ]

    operations = [
        migrations.RunPython(assign_default_roles, reverse_assign_default_roles),
    ]