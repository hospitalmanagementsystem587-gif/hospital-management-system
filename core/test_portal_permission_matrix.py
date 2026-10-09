from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from core.authorization import PORTAL_ALLOWED_GROUPS, user_can_access_portal
from core.models import Patient, PatientAccount, StaffProfile
from core.permission_matrix import PORTAL_PERMISSION_MATRIX, SENSITIVE_DOMAIN_CONTROLS
from core.roles import ROLE_PERMISSIONS, configure_role_permissions

User = get_user_model()


class PortalPermissionMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

    def test_documented_matrix_matches_enforced_portal_groups(self):
        self.assertEqual(set(PORTAL_PERMISSION_MATRIX), {"admin", "staff", "store", "patient", "agent"})
        for portal in ("staff", "store", "patient", "agent"):
            self.assertEqual(PORTAL_PERMISSION_MATRIX[portal]["groups"], PORTAL_ALLOWED_GROUPS[portal])
        self.assertEqual(PORTAL_PERMISSION_MATRIX["admin"]["groups"], frozenset({"Administrator"}))

    def test_unknown_portal_and_inactive_users_fail_closed(self):
        user = User.objects.create_user("matrix_user")
        self.assertFalse(user_can_access_portal(user, "unknown"))
        user.is_active = False
        user.save(update_fields=["is_active"])
        for portal in PORTAL_PERMISSION_MATRIX:
            self.assertFalse(user_can_access_portal(user, portal))

    def test_role_admission_is_explicit_not_navigation_based(self):
        user = User.objects.create_user("matrix_pharmacy")
        user.groups.add(Group.objects.get(name="Pharmacy"))
        StaffProfile.objects.create(user=user, employee_id="MATRIX-PHARM")
        self.assertTrue(user_can_access_portal(user, "store"))
        self.assertTrue(user_can_access_portal(user, "staff"))
        self.assertFalse(user_can_access_portal(user, "agent"))
        self.assertFalse(user_can_access_portal(user, "admin"))

    def test_patient_admission_requires_verified_active_relationship(self):
        user = User.objects.create_user("matrix_patient")
        patient = Patient.objects.create(mrn="MATRIX-1", full_name="Matrix Patient")
        account = PatientAccount.objects.create(user=user, patient=patient, is_verified=False)
        self.assertFalse(user_can_access_portal(user, "patient"))
        account.is_verified = True
        account.save(update_fields=["is_verified"])
        self.assertTrue(user_can_access_portal(user, "patient"))

    def test_sensitive_domains_have_declared_object_controls(self):
        self.assertEqual(
            set(SENSITIVE_DOMAIN_CONTROLS),
            {"clinical_records", "patient_documents", "prescriptions", "pharmacy_stock", "billing", "tickets", "ticket_audit"},
        )
        for role in ("Administrator", "Doctor", "Reception", "Pharmacy", "Support Agent"):
            self.assertIn(role, ROLE_PERMISSIONS)
