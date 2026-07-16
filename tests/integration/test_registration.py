# tests/integration/test_registration.py
"""Integration tests for the registration workflow."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AccountRegistration

User = get_user_model()


class RegistrationPageTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_registration_page_loads(self) -> None:
        response = self.client.get(reverse("registration-page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request Access")

    def test_login_page_has_register_link(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertContains(response, reverse("registration-page"))

    @mock.patch("apps.portal.views_registration.send_registration_verification_email")
    def test_valid_registration_creates_record(self, mock_send) -> None:
        mock_send.return_value = True
        response = self.client.post(reverse("registration-page"), {
            "username": "newengineer",
            "email": "newengineer@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "reason_for_access": "I need access to review RDSO specifications.",
            "department": "Track Engineering",
        })
        self.assertRedirects(response, reverse("registration-done"))
        reg = AccountRegistration.objects.get(username="newengineer")
        self.assertEqual(reg.status, AccountRegistration.Status.PENDING_VERIFICATION)
        self.assertEqual(reg.department, "Track Engineering")
        mock_send.assert_called_once()

    def test_duplicate_username_rejected(self) -> None:
        User.objects.create_user(username="existing", password="pass123")
        response = self.client.post(reverse("registration-page"), {
            "username": "existing",
            "email": "new@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "reason_for_access": "Access needed.",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "username is already taken")

    def test_mismatched_passwords_rejected(self) -> None:
        response = self.client.post(reverse("registration-page"), {
            "username": "newuser",
            "email": "new@example.com",
            "password": "StrongPass123!",
            "password_confirm": "DifferentPass!",
            "reason_for_access": "Access needed.",
        })
        self.assertContains(response, "Passwords do not match")

    def test_weak_password_rejected(self) -> None:
        response = self.client.post(reverse("registration-page"), {
            "username": "newuser",
            "email": "new@example.com",
            "password": "short",
            "password_confirm": "short",
            "reason_for_access": "Access needed.",
        })
        self.assertContains(response, "at least 10 characters")

    def test_registration_done_page_loads(self) -> None:
        response = self.client.get(reverse("registration-done"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration Submitted")

    @mock.patch("apps.portal.views_registration.send_registration_verification_email")
    @mock.patch("apps.portal.views_registration.send_registration_pending_email")
    @mock.patch("apps.portal.views_registration.send_admin_new_registration_notification")
    def test_valid_token_verifies_email_and_advances_status(
        self, mock_admin, mock_pending, mock_verify
    ) -> None:
        mock_verify.return_value = True
        mock_pending.return_value = True
        mock_admin.return_value = True

        reg = AccountRegistration.objects.create(
            email="verify@example.com", username="verifyuser",
            reason_for_access="Test.", password_hash="pbkdf2_sha256$fake",
        )
        token = reg.make_verification_token()

        response = self.client.get(reverse("registration-verify", args=[token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email Verified")

        reg.refresh_from_db()
        self.assertEqual(reg.status, AccountRegistration.Status.PENDING_APPROVAL)
        self.assertIsNotNone(reg.verified_at)

    def test_invalid_token_shows_expired_message(self) -> None:
        response = self.client.get(reverse("registration-verify", args=["bad-token"]))
        self.assertContains(response, "Expired or Invalid")


class AdminRegistrationTests(TestCase):
    def setUp(self) -> None:
        from apps.accounts.models import Role
        self.admin_user = User.objects.create_user(
            username="sysadmin", password="test-pass-123", email="admin@example.com"
        )
        role, _ = Role.objects.get_or_create(
            name="system_admin",
            defaults={"display_name": "System Administrator", "is_system_role": True},
        )
        profile = self.admin_user.profile
        profile.role = role
        profile.save(update_fields=["role"])
        self.client.login(username="sysadmin", password="test-pass-123")

        self.pending_reg = AccountRegistration.objects.create(
            email="applicant@example.com",
            username="applicant",
            first_name="Test",
            last_name="Applicant",
            reason_for_access="Need access for engineering review.",
            password_hash="pbkdf2_sha256$260000$fakehash",
            status=AccountRegistration.Status.PENDING_APPROVAL,
        )

    def test_admin_registrations_page_loads(self) -> None:
        response = self.client.get(reverse("admin-registrations"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "applicant")

    def test_admin_registration_detail_loads(self) -> None:
        response = self.client.get(
            reverse("admin-registration-detail", args=[self.pending_reg.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Need access for engineering review")

    @mock.patch("apps.portal.views_admin.send_registration_approved_email")
    def test_approve_creates_user(self, mock_email) -> None:
        mock_email.return_value = True
        response = self.client.post(
            reverse("admin-registration-detail", args=[self.pending_reg.id]),
            {"action": "approve"},
        )
        self.assertRedirects(response, reverse("admin-registrations"))
        self.pending_reg.refresh_from_db()
        self.assertEqual(self.pending_reg.status, AccountRegistration.Status.APPROVED)
        self.assertIsNotNone(self.pending_reg.approved_user)
        self.assertTrue(User.objects.filter(username="applicant").exists())

    @mock.patch("apps.portal.views_admin.send_registration_rejected_email")
    def test_reject_requires_reason(self, mock_email) -> None:
        response = self.client.post(
            reverse("admin-registration-detail", args=[self.pending_reg.id]),
            {"action": "reject", "rejection_reason": ""},
        )
        self.assertContains(response, "rejection reason is required")
        self.pending_reg.refresh_from_db()
        self.assertEqual(self.pending_reg.status, AccountRegistration.Status.PENDING_APPROVAL)

    @mock.patch("apps.portal.views_admin.send_registration_rejected_email")
    def test_reject_with_reason_updates_status(self, mock_email) -> None:
        mock_email.return_value = True
        self.client.post(
            reverse("admin-registration-detail", args=[self.pending_reg.id]),
            {"action": "reject", "rejection_reason": "Access not justified for this role."},
        )
        self.pending_reg.refresh_from_db()
        self.assertEqual(self.pending_reg.status, AccountRegistration.Status.REJECTED)
        self.assertEqual(
            self.pending_reg.rejection_reason, "Access not justified for this role."
        )
        mock_email.assert_called_once()

    def test_non_admin_cannot_access_admin_portal(self) -> None:
        engineer = User.objects.create_user(username="eng", password="test-pass-123")
        from apps.accounts.models import Role
        role, _ = Role.objects.get_or_create(
            name="engineer",
            defaults={"display_name": "Engineer", "is_system_role": True},
        )
        engineer.profile.role = role
        engineer.profile.save(update_fields=["role"])

        self.client.login(username="eng", password="test-pass-123")
        response = self.client.get(reverse("admin-registrations"))
        self.assertEqual(response.status_code, 403)