import html
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings

from core.models import Department, Specialty
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
class SpecialtyModelCMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Create Administrator user
        cls.admin_user = User.objects.create_user(
            username="admin_cms_user",
            email="admin_cms@hospital.local",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="CMS",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Create Staff user with only view permissions
        cls.staff_view_only = User.objects.create_user(
            username="view_only_user",
            email="viewonly@hospital.local",
            password="ViewPassword123!",
            first_name="View",
            last_name="Only",
            is_staff=True,
        )
        view_perm = Permission.objects.get(codename="view_specialty", content_type__app_label="core")
        cls.staff_view_only.user_permissions.add(view_perm)

        # Create Doctor user (not admin portal staff)
        cls.doctor_user = User.objects.create_user(
            username="doctor_user",
            email="doctor@hospital.local",
            password="DoctorPassword123!",
            first_name="Doctor",
            last_name="Who",
            is_staff=False,
        )
        doctor_group = Group.objects.get(name="Doctor")
        cls.doctor_user.groups.add(doctor_group)

        # Existing department to verify integrity
        cls.dept = Department.objects.create(
            code="GENMED",
            name="General Medicine",
            description="General clinical medicine",
            display_order=1,
            is_active=True,
        )

    def test_specialty_creation_and_attributes(self):
        """Specialty model can be created with code, name, description, icon_name, display_order, is_active."""
        spec = Specialty.objects.create(
            code="CARDIO",
            name="Cardiology",
            description="Comprehensive cardiac diagnostics and care.",
            icon_name="favorite",
            display_order=10,
            is_active=True,
        )
        self.assertEqual(str(spec), "Cardiology")
        self.assertEqual(spec.code, "CARDIO")
        self.assertEqual(spec.display_order, 10)
        self.assertTrue(spec.is_active)
        self.assertEqual(spec._meta.verbose_name, "Specialty")
        self.assertEqual(spec._meta.verbose_name_plural, "Specialties")

    def test_existing_department_data_intact(self):
        """Introducing Specialty model does not alter or corrupt existing Department records."""
        dept = Department.objects.get(code="GENMED")
        self.assertEqual(dept.name, "General Medicine")
        self.assertEqual(dept.display_order, 1)

    def test_authorized_admin_can_view_specialty_changelist(self):
        """Staff with view_specialty permission can access specialty changelist."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/specialty/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)

    def test_authorized_admin_can_create_specialty(self):
        """Administrator can create a new specialty via admin form."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/specialty/add/"
        data = {
            "code": "neuro",
            "name": "Neurology",
            "description": "Brain and nervous system care.",
            "icon_name": "psychology",
            "display_order": "5",
            "is_active": "on",
        }
        response = self.client.post(add_url, data, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        spec = Specialty.objects.filter(code="NEURO").first()
        self.assertIsNotNone(spec)
        self.assertEqual(spec.name, "Neurology")
        self.assertEqual(spec.display_order, 5)
        self.assertTrue(spec.is_active)

    def test_duplicate_code_prevented(self):
        """Case-insensitive duplicate code is rejected by validation."""
        Specialty.objects.create(code="ORTHO", name="Orthopedics")
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/specialty/add/"
        data = {
            "code": "ortho",
            "name": "Orthopedic Surgery",
            "description": "Bone and joint care",
            "icon_name": "medical_services",
            "display_order": "1",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(add_url, data, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("code", form.errors)
        self.assertIn("Specialty with code 'ORTHO' already exists.", form.errors["code"])

    def test_duplicate_name_prevented(self):
        """Case-insensitive duplicate name is rejected by validation."""
        Specialty.objects.create(code="PEDI", name="Pediatrics")
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/specialty/add/"
        data = {
            "code": "PED2",
            "name": "pediatrics",
            "description": "Child care",
            "icon_name": "child_care",
            "display_order": "2",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(add_url, data, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("name", form.errors)
        self.assertIn("Specialty with name 'pediatrics' already exists.", form.errors["name"])

    def test_authorized_admin_can_edit_specialty(self):
        """Administrator can edit existing specialty details."""
        spec = Specialty.objects.create(code="DERM", name="Dermatology", display_order=20)
        self.client.force_login(self.admin_user)
        change_url = f"/admin/core/specialty/{spec.pk}/change/"
        data = {
            "code": "DERM",
            "name": "Dermatology & Skin Care",
            "description": "Skin and aesthetic care.",
            "icon_name": "spa",
            "display_order": "15",
            "is_active": "on",
        }
        response = self.client.post(change_url, data, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        spec.refresh_from_db()
        self.assertEqual(spec.name, "Dermatology & Skin Care")
        self.assertEqual(spec.display_order, 15)

    def test_specialty_ordering(self):
        """Specialties are ordered by display_order then name."""
        Specialty.objects.create(code="S3", name="C Specialty", display_order=30)
        Specialty.objects.create(code="S1", name="A Specialty", display_order=10)
        Specialty.objects.create(code="S2", name="B Specialty", display_order=20)
        ordered_codes = list(Specialty.objects.values_list("code", flat=True))
        self.assertEqual(ordered_codes, ["S1", "S2", "S3"])

    def test_specialty_activation_and_deactivation(self):
        """Specialty active status can be toggled without breaking other records."""
        spec = Specialty.objects.create(code="ENT", name="ENT / Otolaryngology", is_active=True)
        spec.is_active = False
        spec.save(update_fields=["is_active", "updated_at"])
        spec.refresh_from_db()
        self.assertFalse(spec.is_active)

    def test_unauthorized_user_cannot_access_specialty_admin(self):
        """Unauthorized non-staff or other portal roles cannot access specialty admin."""
        self.client.force_login(self.doctor_user)
        response = self.client.get("/admin/core/specialty/", HTTP_HOST="admin.hms.test")
        self.assertIn(response.status_code, [302, 403])

    def test_staff_without_change_permission_cannot_mutate(self):
        """Staff with view-only permissions cannot add or modify specialties."""
        self.client.force_login(self.staff_view_only)
        add_url = "/admin/core/specialty/add/"
        data = {
            "code": "GASTRO",
            "name": "Gastroenterology",
            "display_order": "1",
        }
        response = self.client.post(add_url, data, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Specialty.objects.filter(code="GASTRO").exists())

    def test_xss_content_escaped(self):
        """XSS payloads in specialty name or description are safely HTML escaped."""
        spec = Specialty.objects.create(
            code="XSS",
            name="<script>alert('xss')</script> Oncology",
            description="<img src=x onerror=alert(1)>",
        )
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/specialty/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("<script>alert('xss')</script>", content)
        self.assertIn(html.escape(spec.name), content)
