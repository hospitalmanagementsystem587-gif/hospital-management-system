from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from core.models import Department, DiagnosticTest
from core.roles import configure_role_permissions

User = get_user_model()


@override_settings(
    PORTAL_HOSTS={
        "admin": "admin.hms.test",
        "staff": "staff.hms.test",
        "store": "store.hms.test",
        "patient": "patient.hms.test",
        "agent": "agent.hms.test",
    },
    ALLOWED_HOSTS=["*"],
)
class DiagnosticTestManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user
        cls.admin_user = User.objects.create_user(
            username="admin_diag_user",
            email="admin_diag@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Department
        cls.dept_path = Department.objects.create(
            code="PATH_LAB",
            name="Clinical Pathology",
            display_order=1,
            is_active=True,
        )

        # Baseline diagnostic test
        cls.test_cbc = DiagnosticTest.objects.create(
            code="CBC",
            name="Complete Blood Count",
            category=DiagnosticTest.Category.PATHOLOGY,
            department=cls.dept_path,
            description="Routine hematological examination.",
            preparation_instructions="No fasting required.",
            sample_type="EDTA Whole Blood, 3ml",
            turnaround_time="4 hours",
            display_order=1,
            is_active=True,
        )

    def test_authorized_admin_can_view_diagnostic_test_changelist(self):
        """Admin can view the diagnostic tests catalog changelist."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/diagnostictest/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CBC")
        self.assertContains(response, "Complete Blood Count")
        self.assertContains(response, "Pathology / Laboratory")

    def test_authorized_admin_can_create_diagnostic_test(self):
        """Admin can register a new diagnostic test with clinical metadata."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/diagnostictest/add/"
        payload = {
            "code": "lft_profile",  # Normalizes to LFT_PROFILE
            "name": "Liver Function Test",
            "category": DiagnosticTest.Category.PATHOLOGY,
            "department": str(self.dept_path.pk),
            "description": "Hepatic profile assessing enzymes and proteins.",
            "preparation_instructions": "10-12 hours overnight fasting recommended.",
            "sample_type": "Clotted Blood / Serum",
            "turnaround_time": "6 hours",
            "display_order": "5",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        test = DiagnosticTest.objects.filter(code="LFT_PROFILE").first()
        self.assertIsNotNone(test)
        self.assertEqual(test.name, "Liver Function Test")
        self.assertEqual(test.sample_type, "Clotted Blood / Serum")
        self.assertEqual(test.turnaround_time, "6 hours")
        self.assertTrue(test.is_active)

    def test_duplicate_code_prevented(self):
        """Duplicate test code (case-insensitive) is rejected."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/diagnostictest/add/"
        payload = {
            "code": "cbc",  # Lowercase duplicate
            "name": "CBC Duplicate",
            "category": DiagnosticTest.Category.PATHOLOGY,
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("code", form.errors)
        self.assertIn("Diagnostic test with code 'CBC' already exists.", form.errors["code"])

    def test_duplicate_name_prevented(self):
        """Duplicate test name (case-insensitive) is rejected."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/diagnostictest/add/"
        payload = {
            "code": "CBC_2",
            "name": "complete blood count",  # Lowercase duplicate
            "category": DiagnosticTest.Category.PATHOLOGY,
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("name", form.errors)
        self.assertIn("Diagnostic test with name 'complete blood count' already exists.", form.errors["name"])

    def test_deactivation_does_not_break_catalog_references(self):
        """Deactivating a test toggles is_active safely without deleting records."""
        self.test_cbc.is_active = False
        self.test_cbc.save(update_fields=["is_active", "updated_at"])
        self.test_cbc.refresh_from_db()
        self.assertFalse(self.test_cbc.is_active)
        self.assertEqual(DiagnosticTest.objects.count(), 1)

    def test_unauthorized_user_denied_diagnostic_admin(self):
        """Non-admin and patient portal users cannot access diagnostic test admin."""
        patient_user = User.objects.create_user(username="pat_diag", password="PatPassword123!", is_staff=False)
        self.client.force_login(patient_user)
        response = self.client.get("/admin/core/diagnostictest/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)
