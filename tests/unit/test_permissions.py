# tests/unit/test_permissions.py
"""Unit tests for the RBAC permission system. No database needed."""

from __future__ import annotations

import unittest
from unittest import mock

from apps.accounts.permissions import Permission, ROLE_DEFAULT_PERMISSIONS


class PermissionConstantsTests(unittest.TestCase):
    def test_all_returns_string_list(self) -> None:
        all_perms = Permission.all()
        self.assertIsInstance(all_perms, list)
        self.assertTrue(all(isinstance(p, str) for p in all_perms))

    def test_all_contains_known_permissions(self) -> None:
        all_perms = Permission.all()
        self.assertIn(Permission.VIEW_DOCUMENTS, all_perms)
        self.assertIn(Permission.MANAGE_USERS, all_perms)
        self.assertIn(Permission.UPLOAD_DOCUMENTS, all_perms)

    def test_no_duplicates(self) -> None:
        all_perms = Permission.all()
        self.assertEqual(len(all_perms), len(set(all_perms)))


class RoleDefaultPermissionsTests(unittest.TestCase):
    def test_super_user_has_all_permissions(self) -> None:
        super_user_perms = ROLE_DEFAULT_PERMISSIONS["super_user"]
        for perm in Permission.all():
            self.assertIn(perm, super_user_perms, f"super_user missing: {perm}")

    def test_read_only_has_only_view_permissions(self) -> None:
        read_only_perms = ROLE_DEFAULT_PERMISSIONS["read_only"]
        for perm in read_only_perms:
            self.assertIn("view", perm, f"read_only has non-view permission: {perm}")

    def test_engineer_can_upload_not_delete(self) -> None:
        engineer_perms = ROLE_DEFAULT_PERMISSIONS["engineer"]
        self.assertIn(Permission.UPLOAD_DOCUMENTS, engineer_perms)
        self.assertNotIn(Permission.DELETE_DOCUMENTS, engineer_perms)

    def test_reviewer_cannot_upload(self) -> None:
        reviewer_perms = ROLE_DEFAULT_PERMISSIONS["reviewer"]
        self.assertNotIn(Permission.UPLOAD_DOCUMENTS, reviewer_perms)

    def test_system_admin_can_manage_users(self) -> None:
        sys_admin_perms = ROLE_DEFAULT_PERMISSIONS["system_admin"]
        self.assertIn(Permission.MANAGE_USERS, sys_admin_perms)
        self.assertIn(Permission.APPROVE_REGISTRATIONS, sys_admin_perms)

    def test_document_manager_cannot_manage_users(self) -> None:
        doc_manager_perms = ROLE_DEFAULT_PERMISSIONS["document_manager"]
        self.assertNotIn(Permission.MANAGE_USERS, doc_manager_perms)
        self.assertNotIn(Permission.VIEW_AUDIT_LOGS, doc_manager_perms)

    def test_all_roles_have_at_least_view_documents(self) -> None:
        for role_name, perms in ROLE_DEFAULT_PERMISSIONS.items():
            self.assertIn(
                Permission.VIEW_DOCUMENTS, perms,
                f"Role '{role_name}' is missing VIEW_DOCUMENTS"
            )