# tests/integration/test_accounts.py
"""
Integration tests for RBAC models, permission resolution,
and the requires_permission decorator.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.decorators import requires_permission
from apps.accounts.models import AuditLog, Role, UserProfile
from apps.accounts.permissions import Permission


def _make_user_with_role(username: str, role_name: str) -> tuple[User, UserProfile]:
    user = User.objects.create_user(username=username, password="test-pass-123")
    role = Role.objects.get(name=role_name)
    profile = user.profile  # created by signal
    profile.role = role
    profile.save(update_fields=["role"])
    return user, profile


class UserProfilePermissionTests(TestCase):
    def test_engineer_can_upload_not_manage_users(self) -> None:
        _, profile = _make_user_with_role("eng001", "engineer")
        self.assertTrue(profile.has_permission(Permission.UPLOAD_DOCUMENTS))
        self.assertFalse(profile.has_permission(Permission.MANAGE_USERS))

    def test_read_only_cannot_upload(self) -> None:
        _, profile = _make_user_with_role("read001", "read_only")
        self.assertFalse(profile.has_permission(Permission.UPLOAD_DOCUMENTS))
        self.assertTrue(profile.has_permission(Permission.VIEW_DOCUMENTS))

    def test_system_admin_can_approve_registrations(self) -> None:
        _, profile = _make_user_with_role("admin001", "system_admin")
        self.assertTrue(profile.has_permission(Permission.APPROVE_REGISTRATIONS))

    def test_permission_grant_override(self) -> None:
        _, profile = _make_user_with_role("read002", "read_only")
        self.assertFalse(profile.has_permission(Permission.UPLOAD_DOCUMENTS))
        profile.permission_overrides = {"grant": [Permission.UPLOAD_DOCUMENTS]}
        profile.save(update_fields=["permission_overrides"])
        self.assertTrue(profile.has_permission(Permission.UPLOAD_DOCUMENTS))

    def test_permission_revoke_override(self) -> None:
        _, profile = _make_user_with_role("eng002", "engineer")
        self.assertTrue(profile.has_permission(Permission.UPLOAD_DOCUMENTS))
        profile.permission_overrides = {"revoke": [Permission.UPLOAD_DOCUMENTS]}
        profile.save(update_fields=["permission_overrides"])
        self.assertFalse(profile.has_permission(Permission.UPLOAD_DOCUMENTS))

    def test_superuser_bypasses_rbac(self) -> None:
        superuser = User.objects.create_superuser(username="su", password="test-pass-123")
        # Profile created by signal with no role
        profile = superuser.profile
        profile.role = None
        profile.save(update_fields=["role"])
        # Despite no role, superuser should have all permissions
        self.assertTrue(profile.has_permission(Permission.MANAGE_USERS))
        self.assertTrue(profile.has_permission(Permission.DELETE_DOCUMENTS))

    def test_profile_created_automatically_on_user_creation(self) -> None:
        user = User.objects.create_user(username="auto001", password="test-pass-123")
        self.assertTrue(hasattr(user, "profile"))
        self.assertIsNotNone(user.profile.id)


class RequiresPermissionDecoratorTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _make_request_with_user(self, role_name: str):
        user, _ = _make_user_with_role(f"dec_{role_name}", role_name)
        request = self.factory.get("/fake/")
        request.user = user
        return request

    def test_permitted_user_passes_through(self) -> None:
        request = self._make_request_with_user("engineer")

        @requires_permission(Permission.UPLOAD_DOCUMENTS)
        def fake_view(req):
            return "ok"

        result = fake_view(request)
        self.assertEqual(result, "ok")

    def test_unpermitted_user_raises_permission_denied(self) -> None:
        request = self._make_request_with_user("read_only")

        @requires_permission(Permission.UPLOAD_DOCUMENTS)
        def fake_view(req):
            return "ok"

        with self.assertRaises(PermissionDenied):
            fake_view(request)

    def test_unauthenticated_user_redirected(self) -> None:
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get("/fake/")
        request.user = AnonymousUser()

        @requires_permission(Permission.VIEW_DOCUMENTS)
        def fake_view(req):
            return "ok"

        response = fake_view(request)
        self.assertEqual(response.status_code, 302)


class AuditLogWriteTests(TestCase):
    def test_log_event_creates_record(self) -> None:
        from services.audit.audit_service import log_event
        log_event(
            event_type="auth_login_success",
            actor_id=None,
            actor_username="testuser",
            detail={"test": True},
            ip_address="127.0.0.1",
        )
        self.assertEqual(AuditLog.objects.filter(event_type="auth_login_success").count(), 1)

    def test_log_event_does_not_raise_on_partial_data(self) -> None:
        from services.audit.audit_service import log_event
        # Should not raise even with minimal data
        log_event(event_type="auth_logout")
        self.assertTrue(AuditLog.objects.filter(event_type="auth_logout").exists())

    def test_audit_log_is_immutable_via_admin(self) -> None:
        from django.contrib.admin.sites import site
        from apps.accounts.admin import AuditLogAdmin
        admin_instance = AuditLogAdmin(AuditLog, site)
        mock_request = None
        self.assertFalse(admin_instance.has_add_permission(mock_request))
        self.assertFalse(admin_instance.has_change_permission(mock_request))
        self.assertFalse(admin_instance.has_delete_permission(mock_request))